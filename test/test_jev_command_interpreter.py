"""Contract tests for translation at the Jev adapter boundary."""

import unittest
from types import SimpleNamespace

from backend.jev_command_interpreter import JevCommandInterpreter
from backend.models import CommandIntent, MovePosition, PendingCommand
from backend.player_command import CommandInterpretation


class RecordingTypeSafeClient:
    def __init__(
        self,
        uniqueness: float = 0.1,
        pending_judgments: dict[str, float] | None = None,
        initial_move_requested_confidence: float = 0.0,
    ) -> None:
        self.calls: list[dict] = []
        self.uniqueness = uniqueness
        self.pending_judgments = pending_judgments or {}
        self.initial_move_requested_confidence = initial_move_requested_confidence

    async def system_one(self, *, state: dict, questions: dict):
        self.calls.append({"state": state, "questions": questions})
        return SimpleNamespace(
            choices={
                "intent": SimpleNamespace(choice="show_status", confidence=0.93),
                "position": SimpleNamespace(choice="center", confidence=0.93),
                "position_present": SimpleNamespace(noul=0.1),
                "position_unique": SimpleNamespace(noul=self.uniqueness),
                "initial_move_requested": SimpleNamespace(
                    noul=self.initial_move_requested_confidence
                ),
                **{
                    name: SimpleNamespace(noul=confidence)
                    for name, confidence in self.pending_judgments.items()
                },
            }
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
                "pending_command": None,
            },
        )
        self.assertEqual(
            set(client.calls[0]["questions"]),
            {
                "intent",
                "position",
                "position_present",
                "position_unique",
                "initial_move_requested",
            },
        )
        question = client.calls[0]["questions"]["intent"]
        self.assertEqual(
            set(question.criteria), {intent.value for intent in CommandIntent}
        )

    async def test_position_criteria_cover_row_column_and_numbered_phrases(self) -> None:
        client = RecordingTypeSafeClient()
        interpreter = JevCommandInterpreter(client)

        await interpreter.interpret("row two column three", game_state=None)

        criteria = client.calls[0]["questions"]["position"].criteria
        self.assertIn("row two column three", criteria[MovePosition.MIDDLE_RIGHT.value])
        self.assertIn("cell 6", criteria[MovePosition.MIDDLE_RIGHT.value])

    async def test_start_move_judgment_is_batched_as_an_independent_choice(self) -> None:
        client = RecordingTypeSafeClient(initial_move_requested_confidence=0.91)
        interpretation = await JevCommandInterpreter(client).interpret(
            "start and play the center", game_state=None
        )

        self.assertTrue(interpretation.initial_move_requested)
        self.assertIn("initial_move_requested", client.calls[0]["questions"])

    async def test_pending_request_batches_cancellation_affirmation_and_rejection(self) -> None:
        client = RecordingTypeSafeClient(
            pending_judgments={
                "pending_cancel": 0.91,
                "pending_affirm": 0.82,
                "pending_reject": 0.13,
            }
        )
        interpreter = JevCommandInterpreter(client)

        interpretation = await interpreter.interpret(
            "yes, that works",
            game_state=None,
            pending=PendingCommand(position=MovePosition.CENTER),
        )

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            {
                "pending_cancel",
                "pending_affirm",
                "pending_reject",
            },
            set(client.calls[0]["questions"]) & {
                "pending_cancel",
                "pending_affirm",
                "pending_reject",
            },
        )
        self.assertEqual(
            client.calls[0]["state"]["pending_command"],
            {"intent": "place_move", "position": "center"},
        )
        self.assertEqual(interpretation.cancel_confidence, 0.91)
        self.assertEqual(interpretation.affirm_confidence, 0.82)
        self.assertEqual(interpretation.reject_confidence, 0.13)

    async def test_uncertain_uniqueness_does_not_select_a_position(self) -> None:
        client = RecordingTypeSafeClient(uniqueness=0.5)
        interpretation = await JevCommandInterpreter(client).interpret(
            "play somewhere in the middle", game_state=None
        )

        self.assertIsNone(interpretation.position)


if __name__ == "__main__":
    unittest.main()
