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
    PLACE_MOVE = "place_move"
    THANKS = "thanks"
    GOODBYE = "goodbye"
    UNCLEAR = "unclear"


class MovePosition(str, Enum):
    """The nine unambiguous cells available for a move."""

    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    MIDDLE_LEFT = "middle_left"
    CENTER = "center"
    MIDDLE_RIGHT = "middle_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"

    @property
    def cell_index(self) -> int:
        return list(MovePosition).index(self)

    @property
    def aliases(self) -> tuple[str, ...]:
        return {
            MovePosition.TOP_LEFT: ("upper left", "northwest", "cell 1", "position 1"),
            MovePosition.TOP_CENTER: ("top middle", "upper center", "cell 2", "position 2"),
            MovePosition.TOP_RIGHT: ("upper right", "northeast", "cell 3", "position 3"),
            MovePosition.MIDDLE_LEFT: ("middle left", "center left", "cell 4", "position 4"),
            MovePosition.CENTER: ("middle", "exact center", "cell 5", "position 5"),
            MovePosition.MIDDLE_RIGHT: ("middle right", "center right", "cell 6", "position 6"),
            MovePosition.BOTTOM_LEFT: ("lower left", "southwest", "cell 7", "position 7"),
            MovePosition.BOTTOM_CENTER: ("bottom middle", "lower center", "cell 8", "position 8"),
            MovePosition.BOTTOM_RIGHT: ("lower right", "southeast", "cell 9", "position 9"),
        }[self]


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
    position: MovePosition | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_required: bool
