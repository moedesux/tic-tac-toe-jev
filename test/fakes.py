"""Deterministic test adapters for Player Command acceptance tests."""

from dataclasses import dataclass

from backend.models import GameResponse
from backend.player_command import CommandInterpretation


@dataclass(frozen=True)
class InterpreterCall:
    control: str
    game_state: GameResponse | None


class FakeCommandInterpreter:
    def __init__(self, interpretation: CommandInterpretation) -> None:
        self._interpretation = interpretation
        self.calls: list[InterpreterCall] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
    ) -> CommandInterpretation:
        self.calls.append(InterpreterCall(control, game_state))
        return self._interpretation
