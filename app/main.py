"""
Hex server REST API - wraps MoHex GTP protocol

MoHex uses Go Text Protocol (GTP) for communication.
This API provides a REST interface to MoHex commands.
"""

import subprocess
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# MoHex process and lock for thread-safe access
mohex_process = None
mohex_lock = threading.Lock()


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


def send_gtp_command(command: str) -> str:
    """Send a GTP command to MoHex and return the response."""
    with mohex_lock:
        mohex = get_mohex()
        mohex.stdin.write(command.strip() + "\n")
        mohex.stdin.flush()

        # Read response (GTP responses end with double newline)
        response_lines = []
        while True:
            line = mohex.stdout.readline()
            if line == "\n" and response_lines:
                break
            response_lines.append(line.rstrip("\n"))

        return "\n".join(response_lines)


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
    return jsonify({"success": success, "size": size})


@app.route("/api/clear", methods=["POST"])
def clear_board():
    """Clear the board to start a new game."""
    response = send_gtp_command("clear_board")
    success = response.startswith("=")
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

    return jsonify({"success": success, "color": color, "move": move})


@app.route("/api/genmove", methods=["POST"])
def generate_move():
    """
    Generate the best move for the given color.

    Request body: {"color": "black"}
    Response: {"move": "e5", "success": true}
    """
    data = request.get_json() or {}
    color = data.get("color", "black")

    response = send_gtp_command(f"genmove {color}")
    success = response.startswith("=")
    move = response.lstrip("=? ").strip()

    return jsonify({"success": success, "move": move, "color": color})


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
    return jsonify({"success": success})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8081, debug=True)
