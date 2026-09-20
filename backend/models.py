"""
Pydantic models for API requests and responses.
"""

from enum import Enum

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


class CommandIntent(str, Enum):
    """Meanings supported by the first Player Command slice."""

    GREETING = "greeting"
    START_GAME = "start_game"
    SHOW_BOARD = "show_board"
    SHOW_STATUS = "show_status"
    THANKS = "thanks"
    GOODBYE = "goodbye"
    UNCLEAR = "unclear"


class PlayerCommandRequest(BaseModel):
    """A Natural-Language Control submitted to the command module."""

    control: str = Field(max_length=500)

    @field_validator("control")
    @classmethod
    def control_must_not_be_blank(cls, value: str) -> str:
        control = value.strip()
        if not control:
            raise ValueError("control must not be blank")
        return control


class CommandResult(BaseModel):
    """Provider-neutral result of processing a Player Command."""

    success: bool
    message: str
    intent: CommandIntent
    position: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_required: bool
