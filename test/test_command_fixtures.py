"""Evidence that the shared corpus remains provider-neutral and complete."""

import unittest

from backend.game_session import GameSession
from backend.models import CommandIntent, MovePosition, PendingCommand
from backend.player_command import PlayerCommandProcessor
from test.fakes import FixtureCommandInterpreter, load_command_fixtures


class CommandFixtureCoverageTests(unittest.TestCase):
    def test_corpus_covers_domain_vocabulary_and_risky_behaviors(self) -> None:
        fixtures = load_command_fixtures()
        self.assertEqual(
            {fixture["intent"] for fixture in fixtures},
            {intent.value for intent in CommandIntent},
        )
        self.assertEqual(
            {fixture["position"] for fixture in fixtures if fixture.get("category") == "position"},
            {position.value for position in MovePosition},
        )
        categories = {fixture["category"] for fixture in fixtures}
        self.assertTrue({"board_relative", "ambiguous", "irrelevant"} <= categories)
        self.assertTrue({"pending_missing", "pending_cancel", "pending_affirm", "pending_reject", "start_plus_move", "start_plus_move_missing", "start_plus_move_uncertain"} <= categories)

    def test_every_fixture_executes_through_fake_processor(self) -> None:
        """The corpus is executable deterministic evidence, not just metadata."""
        # Keep this unittest synchronous while using the processor's async seam.
        import asyncio

        async def run() -> None:
            for fixture in load_command_fixtures():
                session = GameSession()
                setup = fixture.get("setup", {})
                if setup.get("moves") or fixture["category"] in {"position", "board_relative", "ambiguous"}:
                    await session.create()
                    for move in setup.get("moves", []):
                        await session.move(move)
                if setup.get("pending"):
                    pending = setup["pending"]
                    async with session.locked():
                        session.set_pending(PendingCommand(
                            intent=pending["intent"],
                            position=MovePosition(pending["position"]) if pending.get("position") else None,
                        ))
                result = await PlayerCommandProcessor(
                    FixtureCommandInterpreter.for_fixture(fixture), session
                ).process(fixture["control"])
                expected = fixture.get("expected", {})
                self.assertEqual(
                    result.intent.value,
                    expected.get("intent", fixture["intent"]),
                )
                if "position" in fixture:
                    self.assertEqual(
                        result.position.value if result.position else None,
                        fixture["position"],
                    )
                if "clarification_required" in expected:
                    self.assertEqual(result.clarification_required, expected["clarification_required"])
                if "board" in expected:
                    self.assertEqual((await session.read()).board, expected["board"])
                if "turn" in expected:
                    self.assertEqual((await session.read()).turn, expected["turn"])
                if "pending" in expected:
                    async with session.locked():
                        actual_pending = session.pending
                    expected_pending = expected["pending"]
                    self.assertEqual(actual_pending is None, expected_pending is None)
                    if actual_pending is not None:
                        self.assertEqual(actual_pending.position, MovePosition(expected_pending["position"]) if expected_pending.get("position") else None)
                    self.assertEqual(result.pending, actual_pending)
                if fixture["category"] in {"ambiguous", "irrelevant", "insufficient_confidence_move", "insufficient_confidence_position", "insufficient_confidence_reset"}:
                    self.assertTrue(result.clarification_required)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
