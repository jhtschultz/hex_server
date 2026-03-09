"""Hex-specific utilities for OpenSpiel integration."""
from __future__ import annotations

import re
from typing import Any, Dict, List

import pyspiel


def ensure_hex_state(state: pyspiel.State) -> pyspiel.State:
    """Assert that the provided state is a Hex state."""
    game_name = state.get_game().get_type().short_name
    if game_name != "hex":
        raise ValueError(f"Expected a Hex state, got {game_name}.")
    return state


def get_board_size(state: pyspiel.State) -> int:
    """Get the board size from the Hex state."""
    game = state.get_game()
    return game.get_parameters().get("board_size", 11)


def action_to_coords(action: int, board_size: int) -> Dict[str, int]:
    """
    Convert an OpenSpiel Hex action to (row, col) coordinates.

    OpenSpiel Hex: action = row * board_size + col
    """
    row = action // board_size
    col = action % board_size
    return {"row": row, "col": col}


def coords_to_action(row: int, col: int, board_size: int) -> int:
    """Convert (row, col) coordinates to OpenSpiel Hex action."""
    return row * board_size + col


def action_to_label(action: int, board_size: int) -> str:
    """
    Convert an OpenSpiel Hex action to human-readable notation.

    Format: A1, B2, etc. (column letter + row number, 1-indexed)
    """
    coords = action_to_coords(action, board_size)
    col_letter = chr(ord('a') + coords["col"])
    row_number = coords["row"] + 1
    return f"{col_letter}{row_number}"


def label_to_action(label: str, board_size: int) -> int:
    """
    Convert human-readable notation to OpenSpiel Hex action.

    Format: A1, B2, etc. (column letter + row number, 1-indexed)
    """
    label = label.strip().lower()
    if len(label) < 2:
        raise ValueError(f"Invalid Hex notation: {label}")

    col_letter = label[0]
    row_str = label[1:]

    col = ord(col_letter) - ord('a')
    row = int(row_str) - 1

    if col < 0 or col >= board_size or row < 0 or row >= board_size:
        raise ValueError(f"Notation {label} out of bounds for {board_size}x{board_size} board")

    return coords_to_action(row, col, board_size)


def extract_board_state(state: pyspiel.State) -> Dict[str, Any]:
    """
    Extract structured board state from OpenSpiel Hex state.

    Returns a dict with:
    - board_size: int
    - board: NxN array where each cell is:
        "EMPTY" = no stone
        "B" = black stone (player 0, connects top-bottom)
        "W" = white stone (player 1, connects left-right)
    - current_player: "B" or "W"
    """
    ensure_hex_state(state)
    board_size = get_board_size(state)

    # Initialize empty board
    board = [["EMPTY" for _ in range(board_size)] for _ in range(board_size)]

    # Parse the text representation
    text = state.to_string()

    # OpenSpiel hex format - parse the board
    # The format shows the board with x for black, o for white, . for empty
    # Each row is indented to show the hex offset
    lines = text.strip().split("\n")

    row_idx = 0
    for line in lines:
        # Skip header/footer lines, look for board content
        # Board lines contain x, o, or . characters
        content = line.strip()
        if not content:
            continue

        # Extract cell values from the line
        cells = []
        for char in content:
            if char == 'x':
                cells.append("B")  # Black (player 0)
            elif char == 'o':
                cells.append("W")  # White (player 1)
            elif char == '.':
                cells.append("EMPTY")

        if len(cells) == board_size and row_idx < board_size:
            board[row_idx] = cells
            row_idx += 1

    current = state.current_player()
    current_player = "B" if current == 0 else "W"

    return {
        "board_size": board_size,
        "board": board,
        "current_player": current_player,
    }


def augment_legal_actions(
    legal_actions: List[Dict[str, Any]],
    board_size: int
) -> List[Dict[str, Any]]:
    """
    Augment legal actions list with parsed coordinate data.

    Each action dict gets additional fields:
    - coords: {row, col} of the cell
    - displayLabel: Human-readable notation (e.g., "a1")
    """
    augmented = []
    for action_entry in legal_actions:
        action_id = action_entry.get("action")
        if action_id is None:
            augmented.append(action_entry)
            continue

        coords = action_to_coords(action_id, board_size)
        display_label = action_to_label(action_id, board_size)

        new_entry = dict(action_entry)
        new_entry["coords"] = coords
        new_entry["displayLabel"] = display_label

        augmented.append(new_entry)

    return augmented
