"""
Hex server REST API - wraps MoHex GTP protocol

MoHex uses Go Text Protocol (GTP) for communication.
This API provides a REST interface to MoHex commands.

Benzene/MoHex source: https://github.com/cgao3/benzene-vanilla-cmake
GTP param commands are registered in:
  - MoHexEngine.cpp        -> param_mohex, param_mohex_policy
  - HexEnvironment.cpp     -> param_player_board, param_player_ice, param_player_vc
  - HexHtpEngine.cpp       -> param_game

Timeout behavior:
  MoHex's max_time param only bounds the MCTS search phase.  The
  pre-search phase (ICE / VCS / decomposition) has NO time limit and
  can hang for 60-120+ seconds on complex positions.

  To guarantee a wall-clock bound, pass {"timeout": <seconds>} in the
  /api/genmove request.  If the first attempt exceeds the timeout the
  engine is restarted with ICE/VCS/decompositions disabled and the
  move is retried.  The response will include "degraded": true and a
  warning.  Short time controls may produce significantly weaker moves
  because the engine loses its primary positional-analysis features.
"""

import logging
import subprocess
import threading

from flask import Flask, request, jsonify

app = Flask(__name__)
log = logging.getLogger(__name__)

# Maps URL-friendly group names to GTP command names.
# See benzene-vanilla-cmake/src for registration points.
PARAM_GROUPS = {
    "mohex": "param_mohex",
    "mohex_policy": "param_mohex_policy",
    "player_board": "param_player_board",
    "player_ice": "param_player_ice",
    "player_vc": "param_player_vc",
    "game": "param_game",
}

# MoHex process and lock for thread-safe access
mohex_process = None
mohex_lock = threading.Lock()

# Game state tracking — needed to replay the position after a
# timeout-triggered engine restart.
# history entries: (color, move) where color is "black" or "white".
_game_state = {"size": 11, "history": []}
_state_lock = threading.Lock()

# Param overrides the user has applied via the API.  Keyed by group
# name so they can be re-applied after an engine restart.
_param_overrides = {}  # {group_name: {key: value, ...}}
_param_lock = threading.Lock()


def get_mohex():
    """Get or create the MoHex process."""
    global mohex_process
    if mohex_process is None or mohex_process.poll() is not None:
        mohex_process = subprocess.Popen(
            ["/opt/benzene/build/src/mohex/mohex"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    return mohex_process


# ── GTP helpers ──────────────────────────────────────────────────────

def _send_gtp(mohex, command: str) -> str:
    """Send a GTP command and block until the response arrives.

    Caller MUST hold mohex_lock.
    """
    mohex.stdin.write(command.strip() + "\n")
    mohex.stdin.flush()

    response_lines = []
    while True:
        line = mohex.stdout.readline()
        if not line:  # EOF — process died
            break
        if line == "\n" and response_lines:
            break
        response_lines.append(line.rstrip("\n"))

    return "\n".join(response_lines)


def _send_gtp_timed(command: str, timeout_seconds) -> tuple:
    """Send a GTP command with a wall-clock timeout.

    Returns (response_str, timed_out).  Caller MUST hold mohex_lock.
    When *timed_out* is True the MoHex process has been killed.
    """
    mohex = get_mohex()

    if timeout_seconds is None:
        return _send_gtp(mohex, command), False

    mohex.stdin.write(command.strip() + "\n")
    mohex.stdin.flush()

    result = [None]

    def _read():
        lines = []
        while True:
            line = mohex.stdout.readline()
            if not line:
                break
            if line == "\n" and lines:
                break
            lines.append(line.rstrip("\n"))
        result[0] = "\n".join(lines)

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()
    reader.join(timeout=timeout_seconds)

    if reader.is_alive():
        # Timed out — kill MoHex so the reader thread unblocks.
        mohex.kill()
        mohex.wait()
        reader.join()
        return None, True

    return result[0], False


def send_gtp_command(command: str) -> str:
    """Send a GTP command to MoHex and return the response."""
    with mohex_lock:
        mohex = get_mohex()
        return _send_gtp(mohex, command)


# ── Engine lifecycle helpers ─────────────────────────────────────────

def _kill_mohex():
    """Kill the current MoHex process.  Caller MUST hold mohex_lock."""
    global mohex_process
    if mohex_process and mohex_process.poll() is None:
        mohex_process.kill()
        mohex_process.wait()
    mohex_process = None


def _replay_position():
    """Replay the tracked game state on a fresh MoHex.

    Caller MUST hold mohex_lock.
    """
    mohex = get_mohex()

    with _state_lock:
        size = _game_state["size"]
        history = list(_game_state["history"])

    _send_gtp(mohex, f"boardsize {size}")
    _send_gtp(mohex, "clear_board")
    for color, move in history:
        _send_gtp(mohex, f"play {color} {move}")


def _restore_params():
    """Re-apply user param overrides on the current MoHex process.

    Caller MUST hold mohex_lock.
    """
    mohex = get_mohex()

    with _param_lock:
        overrides = {g: dict(p) for g, p in _param_overrides.items()}

    for group, params in overrides.items():
        gtp_cmd = PARAM_GROUPS.get(group)
        if not gtp_cmd:
            continue
        for key, value in params.items():
            _send_gtp(mohex, f"{gtp_cmd} {key} {value}")


# ── Endpoints ────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "engine": "mohex"})


@app.route("/api/gtp", methods=["POST"])
def gtp_command():
    """
    Send a raw GTP command to MoHex.

    Request body: {"command": "gtp command string"}
    Response: {"response": "gtp response", "success": true/false}
    """
    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "Missing 'command' in request body"}), 400

    response = send_gtp_command(data["command"])

    # GTP responses start with = (success) or ? (error)
    success = response.startswith("=")
    # Strip the leading = or ? and any ID
    clean_response = response.lstrip("=? ").strip()

    return jsonify({"response": clean_response, "success": success, "raw": response})


@app.route("/api/boardsize", methods=["POST"])
def set_boardsize():
    """
    Set the board size.

    Request body: {"size": 11}
    """
    data = request.get_json()
    size = data.get("size", 11)
    response = send_gtp_command(f"boardsize {size}")
    success = response.startswith("=")
    if success:
        with _state_lock:
            _game_state["size"] = size
            _game_state["history"] = []
    return jsonify({"success": success, "size": size})


@app.route("/api/clear", methods=["POST"])
def clear_board():
    """Clear the board to start a new game."""
    response = send_gtp_command("clear_board")
    success = response.startswith("=")
    if success:
        with _state_lock:
            _game_state["history"] = []
    return jsonify({"success": success})


@app.route("/api/play", methods=["POST"])
def play_move():
    """
    Play a move on the board.

    Request body: {"color": "black", "move": "a1"}
    Color can be "black" or "white" (or "b"/"w")
    Move is a hex coordinate like "a1", "b2", etc.
    """
    data = request.get_json()
    color = data.get("color", "black")
    move = data.get("move")

    if not move:
        return jsonify({"error": "Missing 'move' in request body"}), 400

    response = send_gtp_command(f"play {color} {move}")
    success = response.startswith("=")
    if success:
        with _state_lock:
            _game_state["history"].append((color, move))

    return jsonify({"success": success, "color": color, "move": move})


@app.route("/api/genmove", methods=["POST"])
def generate_move():
    """
    Generate the best move for the given color.

    Request body:
        color:   "black" or "white" (default "black")
        timeout: Optional wall-clock timeout in seconds.  If MoHex
                 does not respond within this limit, the engine is
                 killed, restarted with reduced parameters (ICE, VCS,
                 and decompositions disabled), and the move is retried.
                 The response will include ``"degraded": true``.

                 NOTE: short time controls will produce significantly
                 weaker play because the engine loses its primary
                 positional-analysis features (inferior-cell pruning,
                 virtual connections, and board decomposition).

    Response:
        move:     The engine's chosen move.
        success:  Whether the GTP command succeeded.
        color:    The color that moved.
        degraded: (only on fallback) true.
        warning:  (only on fallback) human-readable explanation.
    """
    data = request.get_json() or {}
    color = data.get("color", "black")
    timeout = data.get("timeout")
    if timeout is not None:
        timeout = float(timeout)

    with mohex_lock:
        # ── First attempt: full-strength search ──────────────────
        response, timed_out = _send_gtp_timed(
            f"genmove {color}", timeout,
        )

        if not timed_out:
            success = response.startswith("=")
            move = response.lstrip("=? ").strip()
            if success:
                with _state_lock:
                    _game_state["history"].append((color, move))
            return jsonify({
                "success": success,
                "move": move,
                "color": color,
            })

        # ── Timeout fallback: restart with reduced params ────────
        log.warning(
            "genmove timed out after %ss — restarting with reduced "
            "params (color=%s, history_len=%d)",
            timeout, color, len(_game_state["history"]),
        )

        _kill_mohex()
        _replay_position()
        _restore_params()

        # Disable the expensive pre-search features that cause hangs.
        mohex = get_mohex()
        _send_gtp(mohex, "param_mohex perform_pre_search 0")
        _send_gtp(mohex, "param_player_board use_ice 0")
        _send_gtp(mohex, "param_player_board use_vcs 0")
        _send_gtp(mohex, "param_player_board use_decompositions 0")

        # Cap MCTS time so it fits within the timeout.  Reserve 2s
        # for overhead (process start, position replay, response).
        if timeout is not None:
            retry_max_time = max(1, int(timeout) - 2)
            _send_gtp(mohex, f"param_mohex max_time {retry_max_time}")

        # Retry — should be fast with analysis features off.
        # Give generous wall-clock since MCTS is now time-bounded.
        retry_timeout = timeout * 2 if timeout else 60
        response, timed_out2 = _send_gtp_timed(
            f"genmove {color}", retry_timeout,
        )

        if timed_out2:
            _kill_mohex()
            log.error(
                "genmove timed out AGAIN with reduced params "
                "(color=%s)", color,
            )
            return jsonify({
                "success": False,
                "error": "genmove timed out even with reduced parameters",
                "color": color,
            }), 504

        success = response.startswith("=")
        move = response.lstrip("=? ").strip()
        if success:
            with _state_lock:
                _game_state["history"].append((color, move))

        # Restore clean state: kill the degraded engine, replay the
        # position (now including the new move), and re-apply the
        # user's original param settings for subsequent calls.
        _kill_mohex()
        _replay_position()
        _restore_params()

        return jsonify({
            "success": success,
            "move": move,
            "color": color,
            "degraded": True,
            "warning": (
                "Move generated with reduced search quality due to "
                "timeout. ICE, VCS, and decompositions were disabled "
                "for this move. Short time controls may produce "
                "significantly weaker play."
            ),
        })


@app.route("/api/play-game", methods=["POST"])
def play_game():
    """
    Reset the board and play a sequence of moves in one call.

    Uses MoHex's native 'play-game' GTP command which does
    clear_board + replay internally — much faster than N separate
    play calls.

    Request body: {"moves": ["a1", "b2", "c3", ...], "size": 11}
    Moves alternate colors starting with black.
    """
    data = request.get_json()
    moves = data.get("moves", [])
    size = data.get("size", 11)

    # Set board size first
    response = send_gtp_command(f"boardsize {size}")
    if not response.startswith("="):
        return jsonify({"success": False, "error": "boardsize failed"}), 500

    # play-game takes space-separated moves, alternating colors
    if moves:
        moves_str = " ".join(moves)
        response = send_gtp_command(f"play-game {moves_str}")
        success = response.startswith("=")
    else:
        response = send_gtp_command("clear_board")
        success = response.startswith("=")

    if success:
        with _state_lock:
            _game_state["size"] = size
            _game_state["history"] = []
            colors = ["black", "white"]
            for i, m in enumerate(moves):
                _game_state["history"].append((colors[i % 2], m))

    return jsonify({"success": success, "moves_played": len(moves)})


def parse_gtp_params(response: str) -> dict:
    """Parse a GTP param response into a dict.

    All Benzene param commands return lines in the format:
        [type] name value
    e.g.:
        [bool] use_ice 1
        [string] max_time 10
    """
    params = {}
    for line in response.split("\n"):
        line = line.strip().lstrip("= ")
        if not line or not line.startswith("["):
            continue
        try:
            bracket_end = line.index("]")
        except ValueError:
            continue
        rest = line[bracket_end + 2:]
        parts = rest.split(None, 1)
        if len(parts) == 2:
            params[parts[0]] = parts[1].strip('"')
    return params


@app.route("/api/param", methods=["GET", "POST"])
@app.route("/api/param/<group>", methods=["GET", "POST"])
def param_handler(group=None):
    """
    Get or set engine parameters for a given param group.

    Groups (see PARAM_GROUPS):
        mohex          - MCTS search params (max_time, max_games, etc.)
        mohex_policy   - Playout policy params
        player_board   - Board-level params (use_ice, use_vcs, use_decompositions)
        player_ice     - ICE (Inferior Cell Engine) params
        player_vc      - VC (Virtual Connection) builder params
        game           - Game-level params (allow_swap, game_time)

    GET /api/param/<group>: Returns all current parameters for the group.
    POST /api/param/<group>: Set one or more parameters.
        Request body: {"param_name": value, ...}

    /api/param is an alias for /api/param/mohex (backward compatible).
    """
    if group is None:
        group = "mohex"
    gtp_cmd = PARAM_GROUPS.get(group)
    if gtp_cmd is None:
        return jsonify({
            "error": f"Unknown param group: {group}",
            "valid_groups": list(PARAM_GROUPS.keys()),
        }), 400

    if request.method == "GET":
        response = send_gtp_command(gtp_cmd)
        success = response.startswith("=")
        return jsonify({
            "success": success,
            "group": group,
            "params": parse_gtp_params(response),
        })

    # POST: set parameters
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    results = {}
    for key, value in data.items():
        response = send_gtp_command(f"{gtp_cmd} {key} {value}")
        success = response.startswith("=")
        results[key] = success
        if success:
            with _param_lock:
                _param_overrides.setdefault(group, {})[key] = value

    return jsonify({
        "success": all(results.values()),
        "group": group,
        "results": results,
    })


@app.route("/api/params", methods=["GET"])
def all_params():
    """Get all parameters from every param group in one call."""
    all_groups = {}
    for group, gtp_cmd in PARAM_GROUPS.items():
        response = send_gtp_command(gtp_cmd)
        all_groups[group] = parse_gtp_params(response)
    return jsonify({"success": True, "params": all_groups})


@app.route("/api/showboard", methods=["GET"])
def show_board():
    """Get ASCII representation of the current board state."""
    response = send_gtp_command("showboard")
    success = response.startswith("=")
    board = response.lstrip("=? ").strip()

    return jsonify({"success": success, "board": board})


@app.route("/api/undo", methods=["POST"])
def undo_move():
    """Undo the last move."""
    response = send_gtp_command("undo")
    success = response.startswith("=")
    if success:
        with _state_lock:
            if _game_state["history"]:
                _game_state["history"].pop()
    return jsonify({"success": success})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8081, debug=True)
