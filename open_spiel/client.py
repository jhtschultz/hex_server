"""HTTP client for the remote MoHex hex server."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class HexClientError(RuntimeError):
    """Base error for Hex client failures."""


class HexTransportError(HexClientError):
    """Raised when the HTTP request to the Hex service fails."""


class HexResponseError(HexClientError):
    """Raised when the Hex service reports a failure."""


@dataclass
class HexResponse:
    """Response from the Hex API genmove endpoint."""

    move: str  # Move notation, e.g., "a1", "f6"
    raw_payload: Dict[str, Any]  # Full response data
    degraded: bool = False  # True if move was generated with reduced params


DEFAULT_HEX_ENDPOINT = (
    "https://hex-server-493397232829.us-central1.run.app"
)


class HexClient:
    """HTTP client for the remote MoHex server."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        *,
        timeout_seconds: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._endpoint = (
            endpoint
            or os.getenv("HEX_ENDPOINT")
            or DEFAULT_HEX_ENDPOINT
        )
        self._timeout_seconds = timeout_seconds or int(
            os.getenv("HEX_TIMEOUT_SECONDS", "60") or "60"
        )
        self._session = session or requests.Session()

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def health(self) -> Dict[str, Any]:
        """Check health of the Hex service."""
        try:
            response = self._session.get(
                f"{self._endpoint}/api/health",
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def clear_board(self) -> Dict[str, Any]:
        """Clear the board to start a new game."""
        try:
            response = self._session.post(
                f"{self._endpoint}/api/clear",
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def set_boardsize(self, size: int) -> Dict[str, Any]:
        """Set the board size."""
        try:
            response = self._session.post(
                f"{self._endpoint}/api/boardsize",
                json={"size": size},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def play(self, color: str, move: str) -> Dict[str, Any]:
        """
        Play a move on the board.

        Args:
            color: "black" or "white"
            move: Move notation, e.g., "a1", "f6"

        Returns:
            Response dict with success status.
        """
        try:
            response = self._session.post(
                f"{self._endpoint}/api/play",
                json={"color": color.lower(), "move": move.lower()},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise HexTransportError(str(exc)) from exc

        data = response.json()
        if not data.get("success"):
            raise HexResponseError(f"Play failed: {data}")
        return data

    def play_game(self, moves: list, size: int = 11) -> Dict[str, Any]:
        """
        Reset the board and play a sequence of moves in one call.

        Uses MoHex's native 'play-game' GTP command — much faster than
        N separate play calls. Moves alternate colors starting with black.

        Args:
            moves: List of move labels, e.g., ["a1", "b2", "c3"]
            size: Board size (default 11)
        """
        try:
            response = self._session.post(
                f"{self._endpoint}/api/play-game",
                json={"moves": moves, "size": size},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                raise HexResponseError(f"play-game failed: {data}")
            return data
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def get_params(self) -> Dict[str, str]:
        """Get all current MoHex engine parameters."""
        try:
            response = self._session.get(
                f"{self._endpoint}/api/param",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("params", {})
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def set_params(self, **params) -> Dict[str, bool]:
        """
        Set MoHex engine parameters.

        Args:
            **params: Parameter name=value pairs, e.g.,
                max_time=5, num_threads=2, max_games=10000
        """
        try:
            response = self._session.post(
                f"{self._endpoint}/api/param",
                json=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                raise HexResponseError(f"set_params failed: {data}")
            return data.get("results", {})
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def get_group_params(self, group: str) -> Dict[str, str]:
        """Get parameters for a specific param group.

        Groups: mohex, mohex_policy, player_board, player_ice,
                player_vc, game
        """
        try:
            response = self._session.get(
                f"{self._endpoint}/api/param/{group}",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("params", {})
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def set_group_params(self, group: str, **params) -> Dict[str, bool]:
        """Set parameters for a specific param group.

        Groups: mohex, mohex_policy, player_board, player_ice,
                player_vc, game

        Example:
            client.set_group_params("player_board", use_ice=0)
        """
        try:
            response = self._session.post(
                f"{self._endpoint}/api/param/{group}",
                json=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                raise HexResponseError(
                    f"set_group_params({group}) failed: {data}"
                )
            return data.get("results", {})
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def get_all_params(self) -> Dict[str, Dict[str, str]]:
        """Get all parameters from every param group at once."""
        try:
            response = self._session.get(
                f"{self._endpoint}/api/params",
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("params", {})
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

    def genmove(
        self,
        color: str,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> HexResponse:
        """
        Request MoHex to generate a move.

        Args:
            color: "black" or "white"
            timeout_seconds: Optional server-side wall-clock timeout.
                If MoHex's pre-search phase (ICE/VCS) exceeds this
                limit, the engine is restarted with those features
                disabled and the move is retried.  The returned
                HexResponse will have ``degraded=True``.

                NOTE: short time controls may produce significantly
                weaker play because the engine loses its primary
                positional-analysis features.

        Returns:
            HexResponse with the engine's chosen move.
        """
        engine_timeout = timeout_seconds or self._timeout_seconds

        # The server-side timeout bounds the engine; the HTTP timeout
        # must be larger to allow for the potential restart+retry.
        http_timeout = engine_timeout * 2 + 10

        payload: Dict[str, Any] = {"color": color.lower()}
        if timeout_seconds is not None:
            payload["timeout"] = engine_timeout

        try:
            response = self._session.post(
                f"{self._endpoint}/api/genmove",
                json=payload,
                timeout=http_timeout,
            )
        except requests.RequestException as exc:
            raise HexTransportError(str(exc)) from exc

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise HexTransportError(str(exc)) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise HexResponseError(
                "Hex service returned invalid JSON."
            ) from exc

        # Engine resigned — position is decided, not an error.
        if data.get("engine_resigned"):
            return HexResponse(
                move=data.get("move", "resign"),
                raw_payload=data,
                degraded=True,
            )

        if not data.get("success"):
            raise HexResponseError(f"Genmove failed: {data}")

        move = data.get("move")
        if not move:
            raise HexResponseError(
                "Hex response missing 'move' field."
            )

        return HexResponse(
            move=move,
            raw_payload=data,
            degraded=bool(data.get("degraded")),
        )
