"""Contract tests for translation at the Jev adapter boundary."""

import unittest
from types import SimpleNamespace

from backend.jev_command_interpreter import JevCommandInterpreter
from backend.models import CommandIntent
from backend.player_command import CommandInterpretation


class RecordingTypeSafeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def system_one(self, *, state: dict, questions: dict):
        self.calls.append({"state": state, "questions": questions})
        return SimpleNamespace(
            choices={"intent": SimpleNamespace(choice="show_status", confidence=0.93)}
        )


class JevCommandInterpreterTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_batched_request_returns_only_domain_values(self) -> None:
        client = RecordingTypeSafeClient()
        interpreter = JevCommandInterpreter(client)

        interpretation = await interpreter.interpret(
            "Whose turn is it?",
            game_state=None,
        )

        self.assertEqual(
            interpretation,
            CommandInterpretation(CommandIntent.SHOW_STATUS, confidence=0.93),
        )
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            client.calls[0]["state"],
            {
                "natural_language_control": "Whose turn is it?",
                "game": None,
            },
        )
        self.assertEqual(
            set(client.calls[0]["questions"]),
            {"intent", "position", "position_present", "position_unique"},
        )
        question = client.calls[0]["questions"]["intent"]
        self.assertEqual(
            set(question.criteria), {intent.value for intent in CommandIntent}
        )


if __name__ == "__main__":
    unittest.main()
