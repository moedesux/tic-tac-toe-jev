"""Acceptance tests for the Player Command processing seam from issue #3."""

import unittest

from backend.game_session import GameSession, NoGameError
from backend.player_command import (
    CommandIntent,
    CommandInterpretation,
    FakeCommandInterpreter,
    PlayerCommandProcessor,
)


class PlayerCommandProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_confident_start_creates_the_only_game(self) -> None:
        session = GameSession()
        interpreter = FakeCommandInterpreter(
            CommandInterpretation(CommandIntent.START_GAME, confidence=0.96)
        )
        processor = PlayerCommandProcessor(interpreter, session)

        result = await processor.process("Let's start a new game", game_state=None)

        self.assertEqual(result.intent, CommandIntent.START_GAME)
        self.assertEqual(result.message, "New game started. X goes first.")
        self.assertEqual(result.confidence, 0.96)
        self.assertFalse(result.clarification_required)
        self.assertIsNone(result.position)
        self.assertEqual((await session.read()).board, [None] * 9)
        self.assertEqual(interpreter.call_count, 1)
        self.assertEqual(interpreter.calls[0].control, "Let's start a new game")
        self.assertIsNone(interpreter.calls[0].game_state)

    async def test_non_start_intents_never_create_a_game(self) -> None:
        expected_messages = {
            CommandIntent.GREETING: "Welcome to Tic-Tac-Toe! Say 'start' to begin a new game.",
            CommandIntent.SHOW_BOARD: "No game has started. Say 'start' to begin a new game.",
            CommandIntent.SHOW_STATUS: "No game has started. Say 'start' to begin a new game.",
            CommandIntent.THANKS: "You're welcome!",
            CommandIntent.GOODBYE: "Thanks for playing! Goodbye!",
            CommandIntent.UNCLEAR: (
                "I didn't understand that. You can start a game, show the board, "
                "check the status, or say goodbye."
            ),
        }

        for intent, message in expected_messages.items():
            with self.subTest(intent=intent):
                session = GameSession()
                processor = PlayerCommandProcessor(
                    FakeCommandInterpreter(CommandInterpretation(intent, 0.91)),
                    session,
                )

                result = await processor.process("anything", game_state=None)

                self.assertEqual(result.message, message)
                self.assertEqual(
                    result.clarification_required,
                    intent is CommandIntent.UNCLEAR,
                )
                with self.assertRaises(NoGameError):
                    await session.read()

    async def test_low_confidence_start_clarifies_without_resetting_game(self) -> None:
        session = GameSession()
        original = await session.create()
        await session.move(0)
        current = await session.read()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(CommandIntent.START_GAME, confidence=0.74)
            ),
            session,
        )

        result = await processor.process("Maybe play again", game_state=current)

        self.assertTrue(result.clarification_required)
        self.assertEqual(result.message, "Would you like to start a new game?")
        unchanged = await session.read()
        self.assertEqual(unchanged.gameId, original.gameId)
        self.assertEqual(unchanged.board[0], "X")

    async def test_board_and_status_messages_are_derived_from_game_state(self) -> None:
        session = GameSession()
        await session.create()
        await session.move(0)
        current = await session.read()

        board_result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(CommandIntent.SHOW_BOARD, confidence=0.88)
            ),
            session,
        ).process("show the board", current)
        status_result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(CommandIntent.SHOW_STATUS, confidence=0.89)
            ),
            session,
        ).process("whose turn is it", current)

        self.assertEqual(board_result.message, "Current board: X . . / . . . / . . .")
        self.assertEqual(status_result.message, "The game is ongoing. It is O's turn.")


if __name__ == "__main__":
    unittest.main()
