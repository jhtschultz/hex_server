"""MoHex bot adapter for OpenSpiel Hex."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pyspiel

from .hex_utils import (
    ensure_hex_state,
    get_board_size,
    action_to_label,
    label_to_action,
)
from .client import HexClient, HexClientError

logger = logging.getLogger(__name__)


class HexBot:
    """Bot that queries a remote MoHex server for Hex moves.

    MoHex engine parameters can be passed as keyword arguments.
    Key parameters:
        max_time:        Seconds per move (default 10)
        max_games:       Max MCTS simulations per move (default 99999999)
        max_nodes:       Max tree nodes (default 11363636)
        max_memory:      Memory limit in bytes (default ~2GB)
        num_threads:     Parallel search threads (default 1)
        use_rave:        Use RAVE values (default 1)
        reuse_subtree:   Reuse search tree between moves (default 1)
        uct_bias_constant:  UCT exploration constant (default 0.22)
        expand_threshold:   Min visits before expanding (default 10)
        knowledge_threshold: Visits before using knowledge (default 256)
        first_play_urgency:  FPU value for unvisited nodes (default 0.35)
        ponder:          Think on opponent's time (default 0)
    """

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        client: Optional[HexClient] = None,
        **mohex_params,
    ) -> None:
        self._client = client or HexClient(
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
        )
        self._timeout_seconds = timeout_seconds
        self._mohex_params = mohex_params
        self._params_applied = False

    def step(self, state: pyspiel.State) -> int:
        """Select an action for the given state (OpenSpiel Bot interface)."""
        hex_state = ensure_hex_state(state)
        legal_actions = hex_state.legal_actions()
        if not legal_actions:
            raise ValueError("HexBot received state with no legal actions.")

        board_size = get_board_size(hex_state)

        label_lookup = {
            action_to_label(action, board_size).lower(): action
            for action in legal_actions
        }

        self._apply_params()
        self._sync_engine_state(hex_state, board_size)

        current_player = hex_state.current_player()
        color = "black" if current_player == 0 else "white"

        try:
            response = self._client.genmove(
                color=color,
                timeout_seconds=self._timeout_seconds,
            )
        except HexClientError as exc:
            raise RuntimeError(f"MoHex client error: {exc}") from exc

        move_label = response.move.lower()
        action = label_lookup.get(move_label)
        if action is None:
            raise ValueError(
                f"MoHex suggested move '{response.move}' which is not legal."
            )
        return action

    def _apply_params(self) -> None:
        """Apply MoHex engine parameters (once)."""
        if self._params_applied or not self._mohex_params:
            return
        try:
            self._client.set_params(**self._mohex_params)
            self._params_applied = True
        except HexClientError as exc:
            logger.warning("Failed to set MoHex params: %s", exc)

    def _sync_engine_state(self, state: pyspiel.State, board_size: int) -> None:
        """Sync the remote engine using MoHex's native play-game command.

        Always sends the full position to avoid stale state — the server
        has a single global board, so we can't trust local caching.
        play-game is ~40ms so the cost is negligible.
        """
        history = state.history()
        moves = [action_to_label(history[i], board_size) for i in range(len(history))]

        try:
            self._client.play_game(moves, size=board_size)
        except HexClientError:
            # Fallback: manual clear + replay
            logger.warning("play-game failed, falling back to manual replay")
            self._client.clear_board()
            self._client.set_boardsize(board_size)
            for i, move in enumerate(moves):
                color = "black" if i % 2 == 0 else "white"
                self._client.play(color, move)
