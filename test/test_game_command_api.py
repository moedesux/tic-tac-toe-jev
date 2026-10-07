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

    async def test_debug_label_sanitizes_without_provider_or_game_operations(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "true", "TYPESAFE_API_KEY": "credential-for-redaction"}):
            async with self.client() as client:
                for control in ["credential-for-redaction start", "Authorization: Bearer private-value", "api_key=private-value", "token: private-value"]:
                    response = await client.post("/api/debug/jev/label", json={"control": control})
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("[redacted]", response.json()["label"])
                    self.assertNotIn("private-value", response.text)
                    self.assertNotIn("credential-for-redaction", response.text)
                ordinary = await client.post("/api/debug/jev/label", json={"control": "play center"})
        self.assertEqual(ordinary.json(), {"label": "play center"})
        self.assertEqual(self.interpreter.call_count, 0)
        with self.assertRaises(NoGameError):
            await self.session.read()

    async def test_disabled_debug_label_discloses_no_command(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "false"}):
            async with self.client() as client:
                response = await client.post("/api/debug/jev/label", json={"control": "private command"})
        self.assertEqual(response.json(), {"label": None})
        self.assertEqual(self.interpreter.call_count, 0)
        with self.assertRaises(NoGameError):
            await self.session.read()

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

    async def test_enabled_capture_contains_actual_provider_exchange(self) -> None:
        from backend.jev_command_interpreter import JevCommandInterpreter
        from test.test_jev_command_interpreter import RecordingTypeSafeClient
        provider = RecordingTypeSafeClient(intent="start_game")
        self.processor = PlayerCommandProcessor(JevCommandInterpreter(provider), self.session)
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "true"}):
            async with self.client() as client:
                response = await client.post("/api/game/command", json={"control": "start"})
                capability = await client.get("/api/debug/jev")
        self.assertEqual(capability.json(), {"enabled": True})
        self.assertEqual(response.status_code, 200)
        exchange = response.json()["jev_exchange"]
        self.assertEqual(exchange["status"], "success")
        self.assertEqual(exchange["request"]["state"], provider.calls[0]["state"])
        self.assertEqual(exchange["request"]["questions"]["intent"]["criteria"], provider.calls[0]["questions"]["intent"].criteria)
        self.assertEqual(exchange["response"]["answers"]["position"]["probabilities"], {"center": .93, "no_match": .07})
        self.assertEqual(exchange["application"]["intent"], "start_game")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual((await self.session.read()).board, [None] * 9)

    async def test_overlapping_capture_is_submission_local_and_sanitized(self) -> None:
        import asyncio
        import json
        from backend.jev_command_interpreter import JevCommandInterpreter
        from test.test_jev_command_interpreter import RecordingTypeSafeClient

        class OverlappingProvider(RecordingTypeSafeClient):
            def __init__(self):
                super().__init__()
                self.first_started = asyncio.Event()
                self.release_first = asyncio.Event()

            async def system_one(self, *, state, questions):
                if state["natural_language_control"] == "first":
                    self.first_started.set()
                    await self.release_first.wait()
                response = await super().system_one(state=state, questions=questions)
                response.request_label = state["natural_language_control"]
                response.authorization = "Bearer private-key"
                response.model = "private-key-provider"
                return response

        provider = OverlappingProvider()
        self.processor = PlayerCommandProcessor(JevCommandInterpreter(provider), self.session)
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "true", "TYPESAFE_API_KEY": "private-key"}):
            async with self.client() as client:
                first = asyncio.create_task(client.post("/api/game/command", json={"control": "first"}))
                await provider.first_started.wait()
                second = await client.post("/api/game/command", json={"control": "second"})
                provider.release_first.set()
                first_response = await first
        for response, control in [(first_response, "first"), (second, "second")]:
            exchange = response.json()["jev_exchange"]
            self.assertEqual(exchange["request"]["state"]["natural_language_control"], control)
            self.assertEqual(exchange["response"]["request_label"], control)
            self.assertNotIn("private-key", json.dumps(exchange))
            self.assertEqual(exchange["response"]["authorization"], "[redacted]")
        self.assertNotEqual(first_response.json()["jev_exchange"]["id"], second.json()["jev_exchange"]["id"])
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "false"}):
            async with self.client() as client:
                disabled = await client.post("/api/game/command", json={"control": "third"})
        self.assertNotIn("jev_exchange", disabled.json())
        self.assertEqual(len(provider.calls), 3)

    async def test_failure_preserves_http_contract_and_originating_request(self) -> None:
        import asyncio
        from typesafe_sdk import TypeSafeAuthenticationError
        from backend.jev_command_interpreter import JevCommandInterpreter
        from test.test_jev_command_interpreter import RecordingTypeSafeClient

        class Provider(RecordingTypeSafeClient):
            def __init__(self):
                super().__init__(intent="greeting")
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def system_one(self, *, state, questions):
                if state["natural_language_control"] == "failure":
                    self.started.set()
                    await self.release.wait()
                    error = TypeSafeAuthenticationError(401, {"message": "Authorization: Bearer unknown-token"}, {"x-typesafe-request-id": "Authorization: Bearer unknown-token private-key"})
                    raise error
                return await super().system_one(state=state, questions=questions)

        provider = Provider()
        self.processor = PlayerCommandProcessor(JevCommandInterpreter(provider), self.session)
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "true", "TYPESAFE_API_KEY": "private-key"}):
            async with self.client() as client:
                failure = asyncio.create_task(client.post("/api/game/command", json={"control": "failure"}))
                await provider.started.wait()
                success = await client.post("/api/game/command", json={"control": "hello"})
                provider.release.set()
                failed = await failure
        self.assertEqual(failed.status_code, 401)
        self.assertEqual(set(failed.json()["detail"]), {"code", "request_id"})
        exchange = failed.json()["jev_exchange"]
        self.assertEqual(exchange["status"], "failure")
        self.assertEqual(exchange["request"]["state"]["natural_language_control"], "failure")
        self.assertEqual(exchange["error"]["kind"], "authentication")
        self.assertEqual(exchange["error"]["code"], failed.json()["detail"]["code"])
        self.assertGreaterEqual(exchange["duration_ms"], 0)
        self.assertIsNone(exchange["response"])
        self.assertNotIn("private-key", failed.text)
        self.assertNotIn("unknown-token", failed.text)
        self.assertNotIn("Authorization", failed.text)
        self.assertEqual(success.json()["jev_exchange"]["status"], "success")
        self.assertEqual(success.json()["jev_exchange"]["request"]["state"]["natural_language_control"], "hello")
        self.assertNotEqual(exchange["id"], success.json()["jev_exchange"]["id"])
        from backend.jev_diagnostics import current_exchange
        self.assertIsNone(current_exchange())
        await self.processor.process("unscoped greeting", None)
        self.assertEqual(exchange["request"]["state"]["natural_language_control"], "failure")
        self.assertIsNone(current_exchange())
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "false"}):
            async with self.client() as client:
                disabled = await client.post("/api/game/command", json={"control": "failure"})
        self.assertEqual(disabled.status_code, 401)
        self.assertEqual(set(disabled.json()), {"detail"})

    async def test_rejected_move_retains_legacy_contract_without_capture(self) -> None:
        from backend.jev_command_interpreter import JevCommandInterpreter
        from test.test_jev_command_interpreter import RecordingTypeSafeClient
        await self.session.create()
        await self.session.move(4)
        provider = RecordingTypeSafeClient(intent="place_move", presence=1, uniqueness=1)
        self.processor = PlayerCommandProcessor(JevCommandInterpreter(provider), self.session)
        with unittest.mock.patch.dict("os.environ", {"JEV_DEBUG": "false"}):
            async with self.client() as client:
                response = await client.post("/api/game/command", json={"control": "center"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["message"], "Position already occupied")
        self.assertNotIn("application_outcome", response.json())
        self.assertNotIn("jev_exchange", response.json())
        self.assertEqual((await self.session.read()).board, [None, None, None, None, "X", None, None, None, None])

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

    async def test_structured_departure_bypasses_interpretation_and_clears_pending(self) -> None:
        await self.session.create()
        async with self.session.locked():
            from backend.models import PendingCommand

            self.session.set_pending(PendingCommand())

        with unittest.mock.patch("backend.main.get_game_session", return_value=self.session):
            async with self.client() as client:
                response = await client.post("/api/game/depart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Thanks for playing! Goodbye!"})
        self.assertIsNone(self.session.pending)
        self.assertEqual(self.interpreter.call_count, 0)
        self.assertEqual((await self.session.read()).status, "ongoing")


if __name__ == "__main__":
    unittest.main()
