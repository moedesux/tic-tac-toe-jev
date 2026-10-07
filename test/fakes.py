"""Deterministic test adapters for Player Command acceptance tests."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from backend.models import CommandIntent, GameResponse, MovePosition, PendingCommand
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


def load_command_fixtures(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the provider-neutral command corpus used by deterministic tests."""
    fixture_path = path or Path(__file__).parent.parent / "fixtures" / "command_behaviors.jsonl"
    return [
        json.loads(line)
        for line in fixture_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class FixtureCommandInterpreter(FakeCommandInterpreter):
    """Fake adapter that maps fixture expectations to domain judgments."""

    @classmethod
    def for_fixture(cls, fixture: dict[str, Any]) -> "FixtureCommandInterpreter":
        position = fixture.get("position")
        return cls(CommandInterpretation(
            intent=CommandIntent(fixture["intent"]),
            confidence=fixture.get("confidence", 0.95),
            position=MovePosition(position) if position else None,
            position_confidence=fixture.get("position_confidence", 0.95 if position else 0.0),
            initial_move_requested=fixture.get("initial_move_requested", False),
            cancel_confidence=fixture.get("cancel_confidence", 0.0),
            affirm_confidence=fixture.get("affirm_confidence", 0.0),
            reject_confidence=fixture.get("reject_confidence", 0.0),
            position_present_confidence=fixture.get("position_present_confidence", 0.95 if position else 0.0),
            position_unique_confidence=fixture.get("position_unique_confidence", 0.95 if position else 0.0),
            initial_move_confidence=fixture.get("initial_move_confidence", 0.95 if fixture.get("initial_move_requested") else 0.0),
            state_change_confidence=fixture.get("state_change_confidence", 1.0),
        ))
