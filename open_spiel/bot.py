"""MoHex bot adapter for OpenSpiel Hex."""
from __future__ import annotations

import logging
from typing import Optional

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
        self._synced_history_len = 0
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
        """Incrementally sync the remote engine to match the current game state.

        On first call or board size change: full clear_board + set_boardsize + replay.
        On subsequent calls: only play moves since last sync.
        """
        history = state.history()

        if self._board_size != board_size or len(history) < self._synced_history_len:
            # New game or board size changed — full reset.
            self._client.clear_board()
            self._client.set_boardsize(board_size)
            self._board_size = board_size
            self._synced_history_len = 0

        # Play only the new moves since last sync.
        for i in range(self._synced_history_len, len(history)):
            player = i % 2
            color = "black" if player == 0 else "white"
            move_label = action_to_label(history[i], board_size)
            self._client.play(color, move_label)

        self._synced_history_len = len(history)
