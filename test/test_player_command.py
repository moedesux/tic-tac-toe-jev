"""Acceptance tests for the Player Command processing seam from issue #3."""

import unittest

from backend.game_session import GameSession, NoGameError
from backend.models import CommandIntent, MovePosition
from backend.player_command import (
    CommandInterpretation,
    PlayerCommandProcessor,
)
from test.fakes import FakeCommandInterpreter


class PlayerCommandProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_confident_move_commands_cover_all_nine_positions(self) -> None:
        for position in MovePosition:
            with self.subTest(position=position):
                session = GameSession()
                await session.create()
                result = await PlayerCommandProcessor(
                    FakeCommandInterpreter(
                        CommandInterpretation(
                            CommandIntent.PLACE_MOVE,
                            confidence=0.95,
                            position=position,
                            position_confidence=0.94,
                        )
                    ),
                    session,
                ).process(f"play at {position.value}", await session.read())

                self.assertFalse(result.clarification_required)
                self.assertEqual(result.position, position)
                self.assertEqual((await session.read()).board.count("X"), 1)

    async def test_move_requires_game_and_does_not_create_one(self) -> None:
        session = GameSession()
        result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    confidence=0.95,
                    position=MovePosition.CENTER,
                    position_confidence=0.95,
                )
            ),
            session,
        ).process("play center", None)

        self.assertTrue(result.clarification_required)
        with self.assertRaises(NoGameError):
            await session.read()

    async def test_ambiguous_move_does_not_mutate_board(self) -> None:
        session = GameSession()
        await session.create()
        before = await session.read()
        result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(CommandIntent.PLACE_MOVE, confidence=0.95)
            ),
            session,
        ).process("play there", before)

        self.assertTrue(result.clarification_required)
        self.assertEqual((await session.read()).board, before.board)

    async def test_occupied_move_is_rejected_by_game_rules(self) -> None:
        session = GameSession()
        await session.create()
        await session.move(4)
        before = await session.read()
        result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    confidence=0.95,
                    position=MovePosition.CENTER,
                    position_confidence=0.95,
                )
            ),
            session,
        ).process("play center", before)

        self.assertIn("Position already occupied", result.message)
        self.assertEqual((await session.read()).board, before.board)

    async def test_command_moves_preserve_win_and_draw_results(self) -> None:
        winning_session = GameSession()
        await winning_session.create()
        for index in (0, 3, 1, 4, 2):
            state = await winning_session.read()
            await PlayerCommandProcessor(
                FakeCommandInterpreter(
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.95,
                        position=list(MovePosition)[index],
                        position_confidence=0.95,
                    )
                ),
                winning_session,
            ).process("play", state)
        winning_state = await winning_session.read()
        self.assertEqual((winning_state.status, winning_state.winner), ("completed", "X"))

        draw_session = GameSession()
        await draw_session.create()
        for index in (0, 1, 2, 4, 3, 5, 7, 6, 8):
            state = await draw_session.read()
            await PlayerCommandProcessor(
                FakeCommandInterpreter(
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.95,
                        position=list(MovePosition)[index],
                        position_confidence=0.95,
                    )
                ),
                draw_session,
            ).process("play", state)
        draw_state = await draw_session.read()
        self.assertEqual((draw_state.status, draw_state.winner), ("draw", None))
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
