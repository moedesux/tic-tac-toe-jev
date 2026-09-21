"""HTTP acceptance tests for the domain-oriented command endpoint."""

import unittest

import httpx

from backend.game_session import GameSession, NoGameError
from backend.main import app, get_command_processor
from backend.models import CommandIntent
from backend.player_command import (
    CommandInterpretation,
    PlayerCommandProcessor,
)
from test.fakes import FakeCommandInterpreter


class GameCommandApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = GameSession()
        self.interpreter = FakeCommandInterpreter(
            CommandInterpretation(CommandIntent.START_GAME, confidence=0.97)
        )
        self.processor = PlayerCommandProcessor(self.interpreter, self.session)
        app.dependency_overrides[get_command_processor] = self._get_processor

    async def _get_processor(self) -> PlayerCommandProcessor:
        return self.processor

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    @staticmethod
    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def test_success_response_has_only_domain_fields(self) -> None:
        async with self.client() as client:
            response = await client.post(
                "/api/game/command",
                json={"control": "Start a game"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "success": True,
                "message": "New game started. X goes first.",
                "intent": "start_game",
                "position": None,
                "confidence": 0.97,
                "clarification_required": False,
                "pending": None,
            },
        )
        self.assertEqual((await self.session.read()).board, [None] * 9)
        self.assertEqual(self.interpreter.call_count, 1)

    async def test_non_start_request_does_not_implicitly_create_game(self) -> None:
        self.interpreter = FakeCommandInterpreter(
            CommandInterpretation(CommandIntent.GREETING, confidence=0.95)
        )
        self.processor = PlayerCommandProcessor(self.interpreter, self.session)
        app.dependency_overrides[get_command_processor] = self._get_processor

        async with self.client() as client:
            response = await client.post(
                "/api/game/command",
                json={"control": "Hello"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["intent"], "greeting")
        with self.assertRaises(NoGameError):
            await self.session.read()

    async def test_empty_control_is_rejected_without_interpretation(self) -> None:
        async with self.client() as client:
            response = await client.post(
                "/api/game/command",
                json={"control": "   "},
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.interpreter.call_count, 0)


if __name__ == "__main__":
    unittest.main()
