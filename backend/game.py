"""
Core game logic for Tic-Tac-Toe.
Handles win detection, validation, and move application.
"""

from typing import List, Optional, Tuple

# Winning combinations: rows, columns, diagonals (immutable)
WINNING_COMBINATIONS: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),  # Rows
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),  # Columns
    (0, 4, 8),
    (2, 4, 6),  # Diagonals
)

ERROR_INVALID_POSITION = "Invalid position"
ERROR_POSITION_OCCUPIED = "Position already occupied"
ERROR_INVALID_TURN = "Invalid turn"


def check_winner(board: List[Optional[str]]) -> Optional[str]:
    """
    Check if there's a winner on the board.

    Args:
        board: List of 9 elements (None, "X", or "O")

    Returns:
        "X" if X wins, "O" if O wins, "draw" if board is full with no winner,
        None if game is still ongoing
    """
    for a, b, c in WINNING_COMBINATIONS:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]

    if all(cell is not None for cell in board):
        return "draw"

    return None


def get_winning_line(board: List[Optional[str]]) -> Optional[Tuple[int, int, int]]:
    """Return the (a, b, c) tuple of winning cells, or None."""
    for combo in WINNING_COMBINATIONS:
        a, b, c = combo
        if board[a] and board[a] == board[b] == board[c]:
            return combo
    return None


def validate_move(
    board: List[Optional[str]], position: int, turn: str
) -> Tuple[bool, str]:
    """
    Validate a move before applying it.

    Args:
        board: Current board state
        position: Position to move (0-8)
        turn: Current player's turn ("X" or "O")

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(position, int) or position < 0 or position > 8:
        return False, ERROR_INVALID_POSITION

    if board[position] is not None:
        return False, ERROR_POSITION_OCCUPIED

    if turn not in ("X", "O"):
        return False, ERROR_INVALID_TURN

    return True, ""


def apply_move(
    board: List[Optional[str]], position: int, turn: str
) -> List[Optional[str]]:
    """
    Apply a move to the board.

    Args:
        board: Current board state
        position: Position to move (0-8)
        turn: Player making the move ("X" or "O")

    Returns:
        New board state with the move applied
    """
    new_board = board.copy()
    new_board[position] = turn
    return new_board
