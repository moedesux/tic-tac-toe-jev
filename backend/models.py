"""
Pydantic models for API requests and responses.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MoveCreate(BaseModel):
    """Model for creating a move."""

    position: int


class GameResponse(BaseModel):
    """Model for game state response."""

    gameId: str
    board: list[str | None]
    turn: str
    winner: str | None
    status: str = Field(
        description="Current game status", pattern="^(ongoing|completed|draw)$"
    )
    gameOver: bool


class GameCommandRequest(BaseModel):
    """A Natural-Language Control submitted to the command module."""

    control: str = Field(max_length=500)

    @field_validator("control")
    @classmethod
    def control_must_not_be_blank(cls, value: str) -> str:
        control = value.strip()
        if not control:
            raise ValueError("control must not be blank")
        return control


class GameCommandResponse(BaseModel):
    """Provider-neutral result of processing a Player Command."""

    success: bool
    message: str
    intent: Literal[
        "greeting",
        "start_game",
        "show_board",
        "show_status",
        "thanks",
        "goodbye",
        "unclear",
    ]
    position: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_required: bool
