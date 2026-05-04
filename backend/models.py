"""
Pydantic models for API requests and responses.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class MoveCreate(BaseModel):
    """Model for creating a move."""

    position: int


class GameResponse(BaseModel):
    """Model for game state response."""

    gameId: str
    board: List[Optional[str]]
    turn: str
    winner: Optional[str]
    status: str = Field(
        description="Current game status", pattern="^(ongoing|completed|draw)$"
    )
    gameOver: bool



