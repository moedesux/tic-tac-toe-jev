"""Voice Game Interface — Wrapper for existing FastAPI backend.

Bridges the voice orchestrator with the existing FastAPI tic-tac-toe backend.
Handles position conversion between 2D (row,col) and 1D (0-8) formats.
"""

from __future__ import annotations

import os
import sys

# Ensure project root is on sys.path for imports
# This handles running the script from any directory
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Also add backend/ so sibling modules (api_endpoints) are importable
_backend_dir = os.path.join(_project_root, "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import requests
from typing import Optional

from config.config import get_voice_config
from config.voice_game_config import ROW_NAMES, COL_NAMES
from api_endpoints import GAMES_ENDPOINT, GAME_BY_ID_ENDPOINT, GAME_MOVES_ENDPOINT


class VoiceGameInterface:
    """Interface to existing FastAPI backend via HTTP."""

    def __init__(self):
        self.game_id: Optional[str] = None
        self._config = None

    def _get_api_base_url(self) -> str:
        """Get the API base URL from config, loading it lazily on first use."""
        if self._config is None:
            self._config = get_voice_config()
        base_url = self._config.api_base_url
        # Ensure both leading and trailing slashes for proper concatenation
        return base_url.rstrip("/") + "/"

    def start_game(self) -> str:
        """Create a new game and return game_id."""
        try:
            response = requests.post(
                f"{self._get_api_base_url()}{GAMES_ENDPOINT}", timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("Backend API timed out. Is the server running?")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Backend API error: {e}")

        data = response.json()
        self.game_id = data["gameId"]
        return self.game_id

    def get_game_state(self) -> dict:
        """Get current game state: board, turn, winner, status."""
        if not self.game_id:
            raise RuntimeError("No active game. Call start_game() first.")

        try:
            response = requests.get(
                f"{self._get_api_base_url()}{GAME_BY_ID_ENDPOINT}", timeout=10
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise RuntimeError("Backend API timed out. Is the server running?")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Backend API error: {e}")

        return response.json()

    def make_move(self, position: int) -> dict:
        """Make a move at position 0-8. Returns updated game state."""
        if not self.game_id:
            raise RuntimeError("No active game. Call start_game() first.")

        try:
            response = requests.post(
                f"{self._get_api_base_url()}{GAME_MOVES_ENDPOINT}",
                json={"position": position},
                timeout=10,
            )
        except requests.exceptions.Timeout:
            raise RuntimeError("Backend API timed out. Is the server running?")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Backend API error: {e}")

        if response.status_code == 400:
            # Extract the detail message from the error response
            try:
                error_detail = response.json().get(
                    "detail", "Invalid move. Please try again."
                )
            except Exception:
                error_detail = "Invalid move. Please try again."
            raise RuntimeError(error_detail)
        response.raise_for_status()
        return response.json()

    def position_to_api(self, row: int, col: int) -> int:
        """Convert 2D coordinates (row, col) to 1D API position (0-8).

        Board layout:
            0  1  2
            3  4  5
            6  7  8

        Args:
            row: Row index (0-2, where 0 is top)
            col: Column index (0-2, where 0 is left)

        Returns:
            Position index (0-8)
        """
        return row * 3 + col

    def position_from_api(self, position: int) -> str:
        """Convert API position (0-8) to readable format.

        Args:
            position: Position index (0-8)

        Returns:
            Human-readable description like "row 1, col 2" or "top-right"
        """
        position = int(position)
        row = position // 3
        col = position % 3

        # Center is special
        if row == 1 and col == 1:
            return "center"

        # Build display name from ROW_NAMES and COL_NAMES (e.g. "top-left")
        return f"{ROW_NAMES[row]}-{COL_NAMES[col]}"

    def board_to_description(self, board: list) -> str:
        """Convert board array to verbal description.

        Args:
            board: List of 9 elements (None, "X", or "O")

        Returns:
            Verbal description of board state
        """
        parts = []
        for pos, cell in enumerate(board):
            if cell is not None:
                pos_desc = self.position_from_api(pos)
                parts.append(f"{cell} at {pos_desc}")

        if parts:
            return f"Board: {', '.join(parts)}"
        return "Empty board"

    def status_to_description(self, status: dict) -> str:
        """Convert game status to verbal description.

        Args:
            status: Game state dict from API

        Returns:
            Verbal status description
        """
        if status["winner"]:
            return f"{status['winner']} has won the game!"
        elif status["status"] == "draw":
            return "It's a draw!"
        elif status["status"] == "ongoing":
            return f"Player {status['turn']}'s turn"
        return "Game ended"
