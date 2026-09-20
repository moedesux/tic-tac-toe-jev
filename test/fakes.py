"""Deterministic test adapters for Player Command acceptance tests."""

from dataclasses import dataclass

from backend.models import GameResponse, PendingCommand
from backend.player_command import CommandInterpretation


@dataclass(frozen=True)
class InterpreterCall:
    control: str
    game_state: GameResponse | None
    pending: PendingCommand | None


class FakeCommandInterpreter:
    def __init__(self, interpretation: CommandInterpretation | list[CommandInterpretation]) -> None:
        self._interpretations = (
            interpretation if isinstance(interpretation, list) else [interpretation]
        )
        self.calls: list[InterpreterCall] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
        pending: PendingCommand | None = None,
    ) -> CommandInterpretation:
        self.calls.append(InterpreterCall(control, game_state, pending))
        index = min(len(self.calls) - 1, len(self._interpretations) - 1)
        return self._interpretations[index]
