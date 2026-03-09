"""MoHex bot adapter for OpenSpiel Hex."""
from __future__ import annotations

import logging
from typing import Optional

import pyspiel

from .hex_utils import (
    ensure_hex_state,
    get_board_size,
    action_to_label,
)
from .client import HexClient, HexClientError

logger = logging.getLogger(__name__)

# Lazy-initialized fallback MCTS bot (one per game config).
_fallback_bots: dict = {}


def _import_mcts():
    """Import OpenSpiel's MCTS module, handling the case where our
    local ``open_spiel`` package shadows the installed one."""
    import importlib
    import sys

    try:
        mod = importlib.import_module("open_spiel.python.algorithms.mcts")
        if hasattr(mod, "MCTSBot"):
            return mod
    except (ImportError, AttributeError):
        pass

    # Local package is shadowing — temporarily evict it from
    # sys.modules and sys.path, import the real one, then restore.
    import site
    saved_path = sys.path[:]
    saved_modules = {
        k: v for k, v in sys.modules.items()
        if k == "open_spiel" or k.startswith("open_spiel.")
    }
    for k in saved_modules:
        del sys.modules[k]

    try:
        # Keep stdlib paths, just remove entries that contain our
        # local open_spiel package (i.e. hex_server dir).
        this_pkg_dir = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
        sys.path = [
            p for p in saved_path if p != this_pkg_dir
        ] + site.getsitepackages() + [site.getusersitepackages()]
        mod = importlib.import_module("open_spiel.python.algorithms.mcts")
        return mod
    finally:
        sys.path = saved_path
        # Keep the real open_spiel.python.* modules in sys.modules
        # so subsequent imports work, but restore our local package.
        sys.modules.update(saved_modules)


def _get_fallback_bot(game: pyspiel.Game):
    """Return a lightweight OpenSpiel MCTS bot for the given game.

    Created once and reused.  Uses random rollouts — weak but legal,
    and only used when MoHex can't generate a move.
    """
    key = id(game)
    if key not in _fallback_bots:
        mcts = _import_mcts()
        _fallback_bots[key] = mcts.MCTSBot(
            game,
            uct_c=2.0,
            max_simulations=200,
            evaluator=mcts.RandomRolloutEvaluator(n_rollouts=5),
            solve=False,
        )
    return _fallback_bots[key]


class HexBot:
    """Bot that queries a remote MoHex server for Hex moves.

    When MoHex cannot generate a move (crash, timeout, or engine
    resignation on proven positions), falls back to OpenSpiel's
    built-in MCTS with random rollouts.  The fallback is weak but
    guarantees a legal move so the game can finish.

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
        self._apply_params()

        current_player = hex_state.current_player()
        color = "black" if current_player == 0 else "white"

        try:
            response = self._client.genmove(
                color=color,
                timeout_seconds=self._timeout_seconds,
            )
        except HexClientError as exc:
            logger.warning("MoHex genmove failed: %s — using fallback MCTS", exc)
            return self._fallback_step(hex_state)

        # Engine resigned or returned an invalid move — fall back.
        raw = response.raw_payload
        if raw.get("engine_resigned"):
            logger.warning(
                "MoHex resigned (position decided) — using fallback MCTS"
            )
            return self._fallback_step(hex_state)

        move_label = response.move.lower()
        action = label_lookup.get(move_label)
        if action is None:
            logger.warning(
                "MoHex returned illegal move '%s' — using fallback MCTS",
                response.move,
            )
            return self._fallback_step(hex_state)

        if response.degraded:
            logger.info("MoHex returned degraded move: %s", response.move)

        return action

    def _fallback_step(self, state: pyspiel.State) -> int:
        """Generate a move using OpenSpiel's built-in MCTS."""
        bot = _get_fallback_bot(state.get_game())
        return bot.step(state)

    def _apply_params(self) -> None:
        """Apply MoHex engine parameters before every genmove.

        Applied after sync (not before) and on every call — params are
        cheap to set and this guards against silent failures that would
        leave MoHex running with defaults (e.g. max_time=10).
        """
        if not self._mohex_params:
            return
        try:
            self._client.set_params(**self._mohex_params)
        except HexClientError as exc:
            raise RuntimeError(
                f"Failed to set MoHex params {self._mohex_params}: {exc}"
            ) from exc

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
