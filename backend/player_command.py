"""Domain-oriented processing for natural-language Player Commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.game_session import GameSession, InvalidMoveError, NoGameError
from backend.models import (
    CommandIntent,
    CommandResult,
    GameResponse,
    MovePosition,
    PendingCommand,
)


@dataclass(frozen=True)
class CommandInterpretation:
    """Provider-neutral interpretation returned across the adapter seam."""

    intent: CommandIntent
    confidence: float
    position: MovePosition | None = None
    position_confidence: float = 0.0
    cancel_confidence: float = 0.0
    affirm_confidence: float = 0.0
    reject_confidence: float = 0.0
    initial_move_requested: bool = False


class CommandInterpreter(Protocol):
    """Asynchronous boundary for interpreting one Natural-Language Control."""

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
        pending: PendingCommand | None = None,
    ) -> CommandInterpretation: ...


class PlayerCommandProcessor:
    """Process one command and own its explicit pending-command transitions."""

    START_CONFIDENCE = 0.80
    BASELINE_CONFIDENCE = 0.60
    MOVE_CONFIDENCE = 0.80
    POSITION_CONFIDENCE = 0.80
    FOLLOW_UP_CONFIDENCE = 0.80

    def __init__(self, interpreter: CommandInterpreter, game_session: GameSession) -> None:
        self._interpreter = interpreter
        self._game_session = game_session

    async def process(
        self,
        control: str,
        game_state: GameResponse | None = None,
    ) -> CommandResult:
        """Interpret once, then apply the resulting transition atomically.

        ``game_state`` remains an accepted argument for callers of the original
        seam. The session snapshot is authoritative so game and pending state
        are always read under the same lock.
        """
        async with self._game_session.locked():
            current_state = self._current_game_unlocked()
            pending = self._game_session.pending

        interpretation = await self._interpreter.interpret(
            control, current_state, pending
        )

        async with self._game_session.locked():
            return self._process_locked(interpretation)

    def _process_locked(self, interpretation: CommandInterpretation) -> CommandResult:
        intent = interpretation.intent
        confidence = interpretation.confidence
        game_state = self._current_game_unlocked()
        pending = self._game_session.pending

        # Cancellation wins if a provider returns overlapping positive
        # judgments. Affirmation and rejection only apply to pending moves.
        if pending and interpretation.cancel_confidence >= self.FOLLOW_UP_CONFIDENCE:
            self._game_session.set_pending(None)
            return self._result(
                CommandIntent.PLACE_MOVE,
                confidence,
                "Okay, I cancelled that move.",
            )

        if (
            pending
            and pending.position is not None
            and interpretation.affirm_confidence >= self.FOLLOW_UP_CONFIDENCE
        ):
            return self._execute_move(pending.position, confidence)

        if pending and interpretation.reject_confidence >= self.FOLLOW_UP_CONFIDENCE:
            replacement = PendingCommand()
            self._game_session.set_pending(replacement)
            return self._result(
                CommandIntent.PLACE_MOVE,
                confidence,
                "Which position would you like to play?",
                clarification=True,
                pending=replacement,
            )

        if confidence < self.BASELINE_CONFIDENCE:
            return self._result(
                intent,
                confidence,
                "I didn't understand that. Could you say it another way?",
                clarification=True,
                pending=pending,
            )

        if intent is CommandIntent.START_GAME:
            if confidence < self.START_CONFIDENCE:
                return self._result(
                    intent,
                    confidence,
                    "Would you like to start a new game?",
                    clarification=True,
                    pending=pending,
                )
            self._game_session.create_locked()
            if interpretation.initial_move_requested:
                return self._handle_move_request(
                    interpretation,
                    intent=CommandIntent.START_GAME,
                )
            return self._result(intent, confidence, "New game started. X goes first.")

        if intent is CommandIntent.PLACE_MOVE:
            if game_state is None:
                return self._result(
                    intent,
                    confidence,
                    "No game has started. Say 'start' to begin a new game.",
                    clarification=True,
                    position=interpretation.position,
                    pending=pending,
                )
            return self._handle_move_request(interpretation, intent=intent)

        if intent is CommandIntent.GREETING:
            message = "Welcome to Tic-Tac-Toe! Say 'start' to begin a new game."
        elif intent is CommandIntent.SHOW_BOARD:
            message = self._board_message(game_state)
        elif intent is CommandIntent.SHOW_STATUS:
            message = self._status_message(game_state)
        elif intent is CommandIntent.THANKS:
            message = "You're welcome!"
        elif intent is CommandIntent.GOODBYE:
            self._game_session.set_pending(None)
            return self._result(intent, confidence, "Thanks for playing! Goodbye!")
        else:
            message = (
                "I didn't understand that. You can start a game, show the board, "
                "check the status, or say goodbye."
            )

        # Social, read-only, and unclear controls do not consume pending state.
        return self._result(
            CommandIntent.UNCLEAR if intent is CommandIntent.UNCLEAR else intent,
            confidence,
            message,
            clarification=intent is CommandIntent.UNCLEAR,
            pending=pending,
        )

    def _handle_move_request(
        self,
        interpretation: CommandInterpretation,
        *,
        intent: CommandIntent,
    ) -> CommandResult:
        position = interpretation.position
        if interpretation.confidence < self.MOVE_CONFIDENCE or position is None:
            pending = PendingCommand(intent=CommandIntent.PLACE_MOVE)
            self._game_session.set_pending(pending)
            return self._result(
                intent,
                interpretation.confidence,
                "Which position would you like to play?",
                clarification=True,
                pending=pending,
            )

        if interpretation.position_confidence < self.POSITION_CONFIDENCE:
            pending = PendingCommand(intent=CommandIntent.PLACE_MOVE, position=position)
            self._game_session.set_pending(pending)
            return self._result(
                intent,
                interpretation.confidence,
                "I heard a move, but I'm not sure which position. Could you be more specific?",
                clarification=True,
                position=position,
                pending=pending,
            )

        return self._execute_move(position, interpretation.confidence)

    def _execute_move(self, position: MovePosition, confidence: float) -> CommandResult:
        # A confident gameplay command replaces stale pending state even when
        # game rules reject its proposed cell.
        self._game_session.set_pending(None)
        try:
            self._game_session.move_locked(position.cell_index)
        except (NoGameError, InvalidMoveError) as error:
            return self._result(
                CommandIntent.PLACE_MOVE,
                confidence,
                str(error),
                position=position,
                pending=None,
            )
        return self._result(
            CommandIntent.PLACE_MOVE,
            confidence,
            f"You placed your mark at {position.value.replace('_', ' ')}.",
            position=position,
        )

    @staticmethod
    def _result(
        intent: CommandIntent,
        confidence: float,
        message: str,
        *,
        clarification: bool = False,
        position: MovePosition | None = None,
        pending: PendingCommand | None = None,
    ) -> CommandResult:
        return CommandResult(
            success=True,
            message=message,
            intent=intent,
            position=position,
            confidence=confidence,
            clarification_required=clarification,
            pending=pending,
        )

    def _current_game_unlocked(self) -> GameResponse | None:
        try:
            return self._game_session.snapshot_locked()
        except NoGameError:
            return None

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
