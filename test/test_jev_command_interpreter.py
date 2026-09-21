"""Contract tests for translation at the Jev adapter boundary."""

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from backend.jev_command_interpreter import JevCommandInterpreter
from backend.models import CommandIntent, GameResponse, MovePosition, PendingCommand
from backend.player_command import CommandInterpretation


class RecordingTypeSafeClient:
    def __init__(
        self,
        uniqueness: float = 0.1,
        presence: float = 0.1,
        intent: str = "show_status",
        position: str = "center",
        pending_judgments: dict[str, float] | None = None,
        initial_move_requested_confidence: float = 0.0,
        state_change_confidence: float = 1.0,
        position_probabilities: dict[str, float] | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.uniqueness = uniqueness
        self.presence = presence
        self.intent = intent
        self.position = position
        self.pending_judgments = pending_judgments or {}
        self.initial_move_requested_confidence = initial_move_requested_confidence
        self.state_change_confidence = state_change_confidence
        self.position_probabilities = position_probabilities or {
            position: 0.93,
            "no_match": 0.07,
        }

    async def system_one(self, *, state: dict, questions: dict):
        self.calls.append({"state": state, "questions": questions})
        return SimpleNamespace(
            choices={
                "intent": SimpleNamespace(choice=self.intent, confidence=0.93),
                "position": SimpleNamespace(
                    choice=self.position,
                    confidence=0.93,
                    probabilities=self.position_probabilities,
                ),
            },
            nouls={
                "position_present": SimpleNamespace(noul=self.presence),
                "position_unique": SimpleNamespace(noul=self.uniqueness),
                "initial_move_requested": SimpleNamespace(
                    noul=self.initial_move_requested_confidence
                ),
                "state_change_requested": SimpleNamespace(
                    noul=self.state_change_confidence
                ),
                **{
                    name: SimpleNamespace(noul=confidence)
                    for name, confidence in self.pending_judgments.items()
                },
            },
        )


class JevCommandInterpreterTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_interpreter_passes_credentials_and_model(self) -> None:
        from backend import jev_command_interpreter

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass

        with patch.dict("os.environ", {"TYPESAFE_API_KEY": "secret", "TYPESAFE_DEFAULT_MODEL": "jev-v1"}), patch.object(jev_command_interpreter, "AsyncTypeSafeClient", FakeClient):
            async with jev_command_interpreter.open_jev_command_interpreter() as interpreter:
                self.assertEqual(interpreter._client.kwargs, {"api_key": "secret", "model": "jev-v1"})
    async def test_one_batched_request_returns_only_domain_values(self) -> None:
        client = RecordingTypeSafeClient()
        interpreter = JevCommandInterpreter(client)

        interpretation = await interpreter.interpret(
            "Whose turn is it?",
            game_state=None,
        )

        self.assertEqual(
            interpretation,
            CommandInterpretation(
                CommandIntent.SHOW_STATUS,
                confidence=0.93,
                position_present_confidence=0.1,
                position_unique_confidence=0.1,
            ),
        )
        self.assertEqual(len(client.calls), 1)
        state = client.calls[0]["state"]
        self.assertEqual(state["natural_language_control"], "Whose turn is it?")
        self.assertIsNone(state["game"])
        self.assertIsNone(state["pending_command"])
        self.assertEqual(state["board"]["lifecycle"], "not_started")
        self.assertEqual(state["board"]["open_cells"], [position.value for position in MovePosition])
        self.assertEqual(state["pending"]["follow_up_options"], [])
        self.assertEqual(
            set(client.calls[0]["questions"]),
            {
                "intent",
                "state_change_requested",
                "position",
                "position_present",
                "position_unique",
                "initial_move_requested",
            },
        )

    async def test_state_change_confidence_gates_a_hedged_move(self) -> None:
        client = RecordingTypeSafeClient(
            intent=CommandIntent.PLACE_MOVE.value,
            presence=0.9,
            uniqueness=0.9,
            state_change_confidence=0.21,
        )

        interpretation = await JevCommandInterpreter(client).interpret(
            "I might play center", game_state=None
        )

        self.assertEqual(interpretation.intent, CommandIntent.PLACE_MOVE)
        self.assertEqual(interpretation.confidence, 0.21)
        self.assertEqual(interpretation.state_change_confidence, 0.21)
        question = client.calls[0]["questions"]["intent"]
        self.assertEqual(
            set(question.criteria), {intent.value for intent in CommandIntent}
        )

    async def test_position_criteria_cover_row_column_and_numbered_phrases(self) -> None:
        client = RecordingTypeSafeClient()
        interpreter = JevCommandInterpreter(client)

        await interpreter.interpret("row two column three", game_state=None)

        criteria = client.calls[0]["questions"]["position"].criteria
        self.assertIn("no_match", criteria)
        self.assertIn("row two column three", criteria[MovePosition.MIDDLE_RIGHT.value])
        self.assertIn("cell 6", criteria[MovePosition.MIDDLE_RIGHT.value])

    async def test_position_choice_can_explicitly_report_no_match(self) -> None:
        client = RecordingTypeSafeClient(
            uniqueness=0.1,
            presence=0.1,
            intent=CommandIntent.PLACE_MOVE.value,
            position="no_match",
        )

        interpretation = await JevCommandInterpreter(client).interpret(
            "play somewhere", game_state=None
        )

        self.assertIsNone(interpretation.position)
        self.assertEqual(interpretation.position_confidence, 0.0)

    async def test_unique_position_recovers_from_a_contradictory_no_match_choice(self) -> None:
        client = RecordingTypeSafeClient(
            uniqueness=0.9,
            presence=0.9,
            intent=CommandIntent.PLACE_MOVE.value,
            position="no_match",
            position_probabilities={"center": 0.44, "no_match": 0.56},
        )

        interpretation = await JevCommandInterpreter(client).interpret(
            "play center", game_state=None
        )

        self.assertEqual(interpretation.position, MovePosition.CENTER)
        self.assertEqual(interpretation.position_confidence, 0.44)

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

    async def test_unique_board_relative_judgment_returns_typed_position_and_full_game_state(self) -> None:
        client = RecordingTypeSafeClient(
            uniqueness=0.94,
            presence=0.96,
            intent=CommandIntent.PLACE_MOVE.value,
            position=MovePosition.MIDDLE_RIGHT.value,
        )
        game_state = GameResponse(
            gameId="game-1",
            board=["X", None, "O", "O", "X", None, None, None, None],
            turn="X",
            winner=None,
            status="ongoing",
            gameOver=False,
        )

        interpretation = await JevCommandInterpreter(client).interpret(
            "play in the only open spot in the middle row",
            game_state,
        )

        self.assertEqual(interpretation.intent, CommandIntent.PLACE_MOVE)
        self.assertEqual(interpretation.position, MovePosition.MIDDLE_RIGHT)
        self.assertEqual(interpretation.position_confidence, 0.93)
        self.assertEqual(
            client.calls[0]["state"]["game"],
            game_state.model_dump(mode="json"),
        )
        self.assertEqual(
            client.calls[0]["state"]["natural_language_control"],
            "play in the only open spot in the middle row",
        )


if __name__ == "__main__":
    unittest.main()
