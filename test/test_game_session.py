"""Acceptance tests for the shared asynchronous game-session boundary.

These tests deliberately use only the public session and REST interfaces.  The
session import is the seam introduced by issue #2; the initial RED run should
fail until the route handlers and in-process callers share that boundary.
"""

import asyncio
import unittest
from unittest.mock import patch

import httpx

from backend import main as main_module
from backend.game_session import GameSession
from backend.main import app, get_game_session


class GameSessionTests(unittest.IsolatedAsyncioTestCase):
    """Verify game behavior through both the in-process and REST boundaries."""

    async def asyncSetUp(self) -> None:
        # Creating through the public REST endpoint gives every test a fresh
        # authoritative game without reaching into module state.
        async with self.client() as client:
            response = await client.post("/api/game")
            self.assertEqual(response.status_code, 200)

    @staticmethod
    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def test_rest_read_and_move_before_create_keep_404_contract(self) -> None:
        # Isolate this public REST scenario from the game created by asyncSetUp.
        isolated_session = GameSession()
        with patch.object(
            main_module, "get_game_session", return_value=isolated_session
        ):
            async with self.client() as client:
                read = await client.get("/api/game")
                self.assertEqual(read.status_code, 404)
                self.assertEqual(read.json(), {"detail": "No game created yet"})

                move = await client.post("/api/game/move", json={"position": 0})
                self.assertEqual(move.status_code, 404)
                self.assertEqual(move.json(), {"detail": "No game created yet"})

    async def test_direct_session_create_read_and_alternating_turns(self) -> None:
        session = get_game_session()
        self.assertIsInstance(session, GameSession)

        created = await session.create()
        self.assertEqual(created.board, [None] * 9)
        self.assertEqual(created.turn, "X")
        self.assertFalse(created.gameOver)

        read = await session.read()
        self.assertEqual(read.gameId, created.gameId)
        self.assertEqual(read.board, [None] * 9)

        after_x = await session.move(0)
        self.assertEqual(after_x.board[0], "X")
        self.assertEqual(after_x.turn, "O")

        after_o = await session.move(4)
        self.assertEqual(after_o.board[4], "O")
        self.assertEqual(after_o.turn, "X")

    async def test_rest_and_direct_calls_share_authoritative_state(self) -> None:
        session = get_game_session()

        async with self.client() as client:
            created = (await client.post("/api/game")).json()
            direct_read = await session.read()
            self.assertEqual(direct_read.gameId, created["gameId"])

            direct_move = await session.move(0)
            self.assertEqual(direct_move.board[0], "X")

            rest_read = await client.get("/api/game")
            self.assertEqual(rest_read.status_code, 200)
            self.assertEqual(rest_read.json()["board"][0], "X")
            self.assertEqual(rest_read.json()["turn"], "O")

            rest_move = await client.post("/api/game/move", json={"position": 4})
            self.assertEqual(rest_move.status_code, 200)
            self.assertEqual(rest_move.json()["board"][4], "O")

            final_read = await session.read()
            self.assertEqual(final_read.board[4], "O")
            self.assertEqual(final_read.turn, "X")

    async def test_invalid_and_occupied_positions_keep_rest_contract(self) -> None:
        async with self.client() as client:
            for position in (-1, 9):
                response = await client.post(
                    "/api/game/move", json={"position": position}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["detail"], "Invalid position")

            first_move = await client.post("/api/game/move", json={"position": 0})
            self.assertEqual(first_move.status_code, 200)

            occupied = await client.post("/api/game/move", json={"position": 0})
            self.assertEqual(occupied.status_code, 400)
            self.assertEqual(
                occupied.json()["detail"], "Position already occupied"
            )

    async def test_win_and_post_game_move_keep_rest_contract(self) -> None:
        async with self.client() as client:
            # X wins across the top row; O's interleaved moves do not win.
            for position in (0, 3, 1, 4, 2):
                response = await client.post(
                    "/api/game/move", json={"position": position}
                )
                self.assertEqual(response.status_code, 200)

            state = response.json()
            self.assertEqual(state["winner"], "X")
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["gameOver"])

            after_game = await client.post("/api/game/move", json={"position": 5})
            self.assertEqual(after_game.status_code, 400)
            self.assertEqual(after_game.json()["detail"], "Game already completed")

    async def test_o_win_keeps_rest_contract(self) -> None:
        async with self.client() as client:
            # O wins across the middle row; X's interleaved moves do not win.
            for position in (0, 3, 1, 4, 8, 5):
                response = await client.post(
                    "/api/game/move", json={"position": position}
                )
                self.assertEqual(response.status_code, 200)

            state = response.json()
            self.assertEqual(state["winner"], "O")
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["gameOver"])

    async def test_draw_keeps_rest_contract(self) -> None:
        async with self.client() as client:
            # No line is completed by either mark in this full-board sequence.
            response = None
            for position in (0, 1, 2, 4, 3, 5, 7, 6, 8):
                response = await client.post(
                    "/api/game/move", json={"position": position}
                )
                self.assertEqual(response.status_code, 200)

            assert response is not None
            state = response.json()
            self.assertIsNone(state["winner"])
            self.assertEqual(state["status"], "draw")
            self.assertTrue(state["gameOver"])

            after_draw = await client.post("/api/game/move", json={"position": 0})
            self.assertEqual(after_draw.status_code, 400)
            self.assertEqual(
                after_draw.json()["detail"], "Position already occupied"
            )

    async def test_concurrent_public_moves_are_serialized(self) -> None:
        session = get_game_session()

        results = await asyncio.gather(session.move(0), session.move(1))
        final_state = await session.read()

        self.assertEqual(
            {final_state.board[0], final_state.board[1]},
            {"X", "O"},
        )
        self.assertEqual(final_state.turn, "X")
        self.assertFalse(final_state.gameOver)
        self.assertTrue(any(result.board[0] == "X" for result in results))
        self.assertTrue(any(result.board[1] == "O" for result in results))


if __name__ == "__main__":
    unittest.main()
