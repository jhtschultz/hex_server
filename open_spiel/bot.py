"""MoHex bot adapter for OpenSpiel Hex."""
from __future__ import annotations

import logging
from typing import List, Optional

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
    """Bot that queries a remote MoHex server for Hex moves."""

    def __init__(
        self,
        *,
        endpoint: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        client: Optional[HexClient] = None,
    ) -> None:
        self._client = client or HexClient(
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
        )
        self._timeout_seconds = timeout_seconds
        self._synced_moves: List[str] = []
        self._board_size: Optional[int] = None

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

    def _sync_engine_state(self, state: pyspiel.State, board_size: int) -> None:
        """Sync the remote engine using MoHex's native play-game command.

        Converts the full history to move labels and sends them in one call.
        Only resends if the history has changed. Falls back to incremental
        play calls if play-game is not available.
        """
        history = state.history()
        moves = [action_to_label(history[i], board_size) for i in range(len(history))]

        # Skip if already synced to this exact position.
        if self._board_size == board_size and moves == self._synced_moves:
            return

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

        self._board_size = board_size
        self._synced_moves = moves
