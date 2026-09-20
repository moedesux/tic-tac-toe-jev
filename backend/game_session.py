"""Asynchronous in-process boundary for the active Tic-Tac-Toe game.

The session is deliberately independent of HTTP.  REST handlers and other
application callers use the same boundary, so there is one authoritative game
state and one lock protecting its transitions.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from backend.game import apply_move, check_winner, validate_move
from backend.models import GameResponse


class GameSessionError(Exception):
    """Base class for errors raised while operating on a game session."""


class NoGameError(GameSessionError):
    """Raised when a game is read or moved before one has been created."""


class InvalidMoveError(GameSessionError):
    """Raised when a move cannot be applied to the active game."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class GameSession:
    """Own the active game and serialize all game state transitions."""

    def __init__(self) -> None:
        self._game: Optional[dict] = None
        self._lock = asyncio.Lock()

    async def create(self) -> GameResponse:
        """Create a fresh game, replacing the current game if one exists."""
        async with self._lock:
            self._game = self._initial_game()
            return self._response()

    async def ensure_created(self) -> GameResponse:
        """Return the active game, creating one when no game exists."""
        async with self._lock:
            if self._game is None:
                self._game = self._initial_game()
            return self._response()

    async def read(self) -> GameResponse:
        """Return the active game or raise when no game exists."""
        async with self._lock:
            self._require_game()
            return self._response()

    async def move(self, position: int) -> GameResponse:
        """Apply a move to the active game and return its new state."""
        async with self._lock:
            game = self._require_game()
            board = game["board"]
            turn = game["turn"]

            is_valid, error_message = validate_move(board, position, turn)
            if not is_valid:
                raise InvalidMoveError(error_message)

            # Keep the existing API contract: a completed game rejects a move
            # before applying any further domain transition.
            winner = check_winner(board)
            if winner in ("X", "O"):
                raise InvalidMoveError("Game already completed")

            new_board = apply_move(board, position, turn)
            next_turn = "O" if turn == "X" else "X"
            new_winner = check_winner(new_board)

            game["board"] = new_board
            game["turn"] = next_turn
            game["winner"] = new_winner if new_winner in ("X", "O") else None
            game["status"] = (
                "completed"
                if new_winner in ("X", "O")
                else ("draw" if new_winner == "draw" else "ongoing")
            )
            game["gameOver"] = new_winner is not None

            return self._response()

    @staticmethod
    def _initial_game() -> dict:
        return {
            "gameId": str(uuid.uuid4()),
            "board": [None] * 9,
            "turn": "X",
            "winner": None,
            "status": "ongoing",
            "gameOver": False,
        }

    def _require_game(self) -> dict:
        if self._game is None:
            raise NoGameError("No game created yet")
        return self._game

    def _response(self) -> GameResponse:
        return GameResponse(**self._require_game())
