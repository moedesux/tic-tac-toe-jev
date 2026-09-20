"""Domain-oriented processing for natural-language Player Commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.game_session import GameSession
from backend.models import CommandIntent, CommandResult, GameResponse


@dataclass(frozen=True)
class CommandInterpretation:
    """Provider-neutral interpretation returned across the adapter seam."""

    intent: CommandIntent
    confidence: float


class CommandInterpreter(Protocol):
    """Asynchronous boundary for interpreting one Natural-Language Control."""

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
    ) -> CommandInterpretation: ...


class PlayerCommandProcessor:
    """Interpret and execute the baseline Player Command intents."""

    START_CONFIDENCE = 0.80
    BASELINE_CONFIDENCE = 0.60

    def __init__(
        self,
        interpreter: CommandInterpreter,
        game_session: GameSession,
    ) -> None:
        self._interpreter = interpreter
        self._game_session = game_session

    async def process(
        self,
        control: str,
        game_state: GameResponse | None,
    ) -> CommandResult:
        """Process one non-empty control against the supplied game state."""
        interpretation = await self._interpreter.interpret(control, game_state)
        intent = interpretation.intent
        confidence = interpretation.confidence

        if confidence < self.BASELINE_CONFIDENCE:
            return self._result(
                intent,
                confidence,
                "I didn't understand that. Could you say it another way?",
                clarification=True,
            )

        if intent is CommandIntent.START_GAME:
            if confidence < self.START_CONFIDENCE:
                return self._result(
                    intent,
                    confidence,
                    "Would you like to start a new game?",
                    clarification=True,
                )
            await self._game_session.create()
            return self._result(
                intent,
                confidence,
                "New game started. X goes first.",
            )

        if intent is CommandIntent.GREETING:
            message = "Welcome to Tic-Tac-Toe! Say 'start' to begin a new game."
        elif intent is CommandIntent.SHOW_BOARD:
            message = self._board_message(game_state)
        elif intent is CommandIntent.SHOW_STATUS:
            message = self._status_message(game_state)
        elif intent is CommandIntent.THANKS:
            message = "You're welcome!"
        elif intent is CommandIntent.GOODBYE:
            message = "Thanks for playing! Goodbye!"
        else:
            return self._result(
                CommandIntent.UNCLEAR,
                confidence,
                "I didn't understand that. You can start a game, show the board, "
                "check the status, or say goodbye.",
                clarification=True,
            )

        return self._result(intent, confidence, message)

    @staticmethod
    def _result(
        intent: CommandIntent,
        confidence: float,
        message: str,
        *,
        clarification: bool = False,
    ) -> CommandResult:
        return CommandResult(
            success=True,
            message=message,
            intent=intent,
            confidence=confidence,
            clarification_required=clarification,
        )

    @staticmethod
    def _board_message(game_state: GameResponse | None) -> str:
        if game_state is None:
            return "No game has started. Say 'start' to begin a new game."
        cells = [cell or "." for cell in game_state.board]
        rows = (" ".join(cells[index : index + 3]) for index in range(0, 9, 3))
        return f"Current board: {' / '.join(rows)}"

    @staticmethod
    def _status_message(game_state: GameResponse | None) -> str:
        if game_state is None:
            return "No game has started. Say 'start' to begin a new game."
        if game_state.status == "draw":
            return "The game ended in a draw."
        if game_state.status == "completed":
            return f"The game is complete. {game_state.winner} won."
        return f"The game is ongoing. It is {game_state.turn}'s turn."
