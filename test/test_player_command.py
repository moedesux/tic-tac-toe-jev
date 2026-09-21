"""Acceptance tests for the Player Command processing seam from issue #3."""

import unittest

from backend.game_session import GameSession, NoGameError
from backend.jev_command_interpreter import JevCommandInterpreter
from backend.models import CommandIntent, MovePosition, PendingCommand
from backend.player_command import (
    CommandInterpretation,
    PlayerCommandProcessor,
)
from test.test_jev_command_interpreter import RecordingTypeSafeClient
from test.fakes import FakeCommandInterpreter


class PlayerCommandProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unique_board_relative_adapter_move_applies_current_mark_and_alternates(self) -> None:
        session = GameSession()
        await session.create()
        for index in (0, 2, 3, 4):
            await session.move(index)

        client = RecordingTypeSafeClient(
            uniqueness=0.94,
            presence=0.96,
            intent=CommandIntent.PLACE_MOVE.value,
            position=MovePosition.MIDDLE_RIGHT.value,
        )
        result = await PlayerCommandProcessor(
            JevCommandInterpreter(client), session
        ).process(
            "play in the only open spot in the middle row",
            await session.read(),
        )

        state = await session.read()
        self.assertEqual(result.position, MovePosition.MIDDLE_RIGHT)
        self.assertEqual(state.board[MovePosition.MIDDLE_RIGHT.cell_index], "X")
        self.assertEqual(state.turn, "O")

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

    async def test_uncertain_position_clarifies_without_mutation(self) -> None:
        session = GameSession()
        await session.create()
        before = await session.read()
        result = await PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    confidence=0.95,
                    position=None,
                    position_confidence=0.0,
                )
            ),
            session,
        ).process("play somewhere in the middle", before)

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

    async def test_start_with_precise_initial_move_is_one_atomic_start_transition(self) -> None:
        session = GameSession()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.START_GAME,
                    0.96,
                    position=MovePosition.CENTER,
                    position_confidence=0.97,
                    initial_move_requested=True,
                )
            ),
            session,
        )

        result = await processor.process("start and play center")

        self.assertEqual(result.intent, CommandIntent.START_GAME)
        self.assertEqual(result.position, MovePosition.CENTER)
        self.assertFalse(result.clarification_required)
        self.assertIn("center", result.message)
        self.assertEqual((await session.read()).board[4], "X")
        async with session.locked():
            self.assertIsNone(session.pending)

    async def test_start_with_missing_initial_position_starts_and_waits_for_position(self) -> None:
        session = GameSession()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.START_GAME,
                    0.96,
                    initial_move_requested=True,
                )
            ),
            session,
        )

        result = await processor.process("start and make a move")

        self.assertEqual(result.intent, CommandIntent.START_GAME)
        self.assertTrue(result.clarification_required)
        self.assertEqual(result.pending, PendingCommand(intent=CommandIntent.PLACE_MOVE))
        self.assertEqual((await session.read()).board, [None] * 9)
        async with session.locked():
            self.assertEqual(
                session.pending,
                PendingCommand(intent=CommandIntent.PLACE_MOVE),
            )

    async def test_start_with_uncertain_initial_position_starts_without_moving(self) -> None:
        session = GameSession()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.START_GAME,
                    0.96,
                    position=MovePosition.CENTER,
                    position_confidence=0.79,
                    initial_move_requested=True,
                )
            ),
            session,
        )

        result = await processor.process("start and maybe play the middle")

        self.assertEqual(result.intent, CommandIntent.START_GAME)
        self.assertTrue(result.clarification_required)
        self.assertEqual(result.pending.position, MovePosition.CENTER)
        self.assertEqual((await session.read()).board, [None] * 9)
        async with session.locked():
            self.assertEqual(session.pending, result.pending)

    async def test_unsupported_compound_executes_only_the_selected_action(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                CommandInterpretation(
                    CommandIntent.SHOW_BOARD,
                    0.96,
                    position=MovePosition.CENTER,
                    position_confidence=0.97,
                    initial_move_requested=True,
                )
            ),
            session,
        )

        result = await processor.process("show the board and play center")

        self.assertEqual(result.intent, CommandIntent.SHOW_BOARD)
        self.assertIsNone(result.position)
        self.assertFalse(result.clarification_required)
        self.assertEqual((await session.read()).board, [None] * 9)

    async def test_existing_game_requires_stricter_confidence_to_reset_for_start(self) -> None:
        session = GameSession()
        original = await session.create()
        await session.move(MovePosition.TOP_LEFT.cell_index)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(CommandInterpretation(CommandIntent.START_GAME, 0.85)),
            session,
        )

        result = await processor.process("start over")

        self.assertTrue(result.clarification_required)
        unchanged = await session.read()
        self.assertEqual(unchanged.gameId, original.gameId)
        self.assertEqual(unchanged.board[0], "X")

    async def test_high_confidence_start_can_reset_existing_game(self) -> None:
        session = GameSession()
        original = await session.create()
        await session.move(MovePosition.TOP_LEFT.cell_index)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(CommandInterpretation(CommandIntent.START_GAME, 0.95)),
            session,
        )

        result = await processor.process("start over")

        self.assertFalse(result.clarification_required)
        restarted = await session.read()
        self.assertNotEqual(restarted.gameId, original.gameId)
        self.assertEqual(restarted.board, [None] * 9)

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

    async def test_missing_position_is_completed_by_follow_up_position(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    0.94,
                    position=MovePosition.CENTER,
                    position_confidence=0.95,
                ),
            ]),
            session,
        )

        pending_result = await processor.process("play a move")
        self.assertTrue(pending_result.clarification_required)
        self.assertIsNotNone(pending_result.pending)
        completed_result = await processor.process("the center")

        self.assertFalse(completed_result.clarification_required)
        self.assertIsNone(completed_result.pending)
        self.assertEqual((await session.read()).board[4], "X")

    async def test_proposed_position_requires_affirmation_and_rejection_reopens_choice(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    0.95,
                    position=MovePosition.CENTER,
                    position_confidence=0.70,
                ),
                CommandInterpretation(
                    CommandIntent.UNCLEAR,
                    0.92,
                    affirm_confidence=0.90,
                ),
            ]),
            session,
        )

        proposed = await processor.process("maybe center")
        self.assertTrue(proposed.clarification_required)
        self.assertEqual((await session.read()).board, [None] * 9)
        affirmed = await processor.process("yes")

        self.assertFalse(affirmed.clarification_required)
        self.assertEqual((await session.read()).board[4], "X")

        rejection_processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE,
                    0.95,
                    position=MovePosition.TOP_LEFT,
                    position_confidence=0.70,
                ),
                CommandInterpretation(
                    CommandIntent.UNCLEAR,
                    0.92,
                    reject_confidence=0.90,
                ),
            ]),
            session,
        )
        await rejection_processor.process("maybe top left")
        rejected = await rejection_processor.process("no")
        self.assertTrue(rejected.clarification_required)
        self.assertIsNotNone(rejected.pending)
        self.assertIsNone(rejected.pending.position)

    async def test_cancellation_and_social_follow_up_preserve_expected_pending_state(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                CommandInterpretation(CommandIntent.GREETING, 0.92),
                CommandInterpretation(CommandIntent.THANKS, 0.92),
                CommandInterpretation(CommandIntent.UNCLEAR, 0.92),
                CommandInterpretation(CommandIntent.UNCLEAR, 0.92, cancel_confidence=0.90),
            ]),
            session,
        )

        await processor.process("play")
        greeting = await processor.process("hello")
        self.assertIsNotNone(greeting.pending)
        thanks = await processor.process("thanks")
        self.assertIsNotNone(thanks.pending)
        unclear = await processor.process("what")
        self.assertIsNotNone(unclear.pending)
        cancelled = await processor.process("cancel")
        self.assertIsNone(cancelled.pending)
        self.assertIsNone(session.pending)

    async def test_low_confidence_follow_up_preserves_pending(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                CommandInterpretation(CommandIntent.UNCLEAR, 0.40),
            ]),
            session,
        )
        await processor.process("play")
        result = await processor.process("uh")
        self.assertTrue(result.clarification_required)
        self.assertIsNotNone(result.pending)
        self.assertIsNotNone(session.pending)

    async def test_confident_replacement_clears_pending_even_when_cell_is_invalid(self) -> None:
        session = GameSession()
        await session.create()
        await session.move(4)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE, 0.95,
                    position=MovePosition.TOP_LEFT, position_confidence=0.70,
                ),
                CommandInterpretation(
                    CommandIntent.PLACE_MOVE, 0.95,
                    position=MovePosition.CENTER, position_confidence=0.95,
                ),
            ]),
            session,
        )
        await processor.process("maybe top left")
        result = await processor.process("play center")
        self.assertIn("occupied", result.message)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)

    async def test_new_game_and_departure_clear_pending(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter([
                CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                CommandInterpretation(CommandIntent.START_GAME, 0.95),
                CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                CommandInterpretation(CommandIntent.GOODBYE, 0.95),
            ]),
            session,
        )
        await processor.process("play")
        await processor.process("new game")
        self.assertIsNone(session.pending)
        await processor.process("play")
        result = await processor.process("goodbye")
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)

    async def test_completed_game_clears_pending(self) -> None:
        session = GameSession()
        await session.create()
        for index in (0, 3, 1, 4):
            await session.move(index)
        async with session.locked():
            session.set_pending(PendingCommand())
        await session.move(2)
        self.assertIsNone(session.pending)

    async def test_confident_gameplay_replaces_pending_move(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.95,
                        position=MovePosition.TOP_LEFT,
                        position_confidence=0.95,
                    ),
                ]
            ),
            session,
        )

        await processor.process("play")
        result = await processor.process("play top left")

        self.assertFalse(result.clarification_required)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)
        self.assertEqual((await session.read()).board[0], "X")

    async def test_invalid_confident_replacement_also_clears_pending_move(self) -> None:
        session = GameSession()
        await session.create()
        await session.move(MovePosition.CENTER.cell_index)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.95,
                        position=MovePosition.CENTER,
                        position_confidence=0.95,
                    ),
                ]
            ),
            session,
        )

        await processor.process("play")
        result = await processor.process("play center")

        self.assertIn("Position already occupied", result.message)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)
        self.assertEqual((await session.read()).board[4], "X")

    async def test_low_confidence_follow_up_preserves_pending_move(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.40,
                        position=MovePosition.TOP_LEFT,
                        position_confidence=0.95,
                    ),
                ]
            ),
            session,
        )

        pending_result = await processor.process("play")
        result = await processor.process("maybe top left")

        self.assertTrue(result.clarification_required)
        self.assertEqual(result.pending, pending_result.pending)
        self.assertEqual((await session.read()).board, [None] * 9)
        self.assertEqual(session.pending, pending_result.pending)

    async def test_new_game_clears_pending_move_and_replaces_state(self) -> None:
        session = GameSession()
        original = await session.create()
        await session.move(MovePosition.TOP_LEFT.cell_index)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(CommandIntent.START_GAME, 0.95),
                ]
            ),
            session,
        )

        await processor.process("play")
        result = await processor.process("start over")
        restarted = await session.read()

        self.assertEqual(result.intent, CommandIntent.START_GAME)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)
        self.assertNotEqual(restarted.gameId, original.gameId)
        self.assertEqual(restarted.board, [None] * 9)

    async def test_game_completion_clears_pending_move(self) -> None:
        session = GameSession()
        await session.create()
        for position in (0, 3, 1, 4):
            await session.move(position)
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        0.95,
                        position=MovePosition.TOP_RIGHT,
                        position_confidence=0.95,
                    ),
                ]
            ),
            session,
        )

        await processor.process("play")
        result = await processor.process("play top right")
        completed = await session.read()

        self.assertFalse(result.clarification_required)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)
        self.assertEqual((completed.status, completed.winner), ("completed", "X"))

    async def test_departure_clears_pending_move(self) -> None:
        session = GameSession()
        await session.create()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.PLACE_MOVE, 0.95),
                    CommandInterpretation(CommandIntent.GOODBYE, 0.95),
                ]
            ),
            session,
        )

        await processor.process("play")
        result = await processor.process("goodbye")

        self.assertEqual(result.intent, CommandIntent.GOODBYE)
        self.assertIsNone(result.pending)
        self.assertIsNone(session.pending)


if __name__ == "__main__":
    unittest.main()
