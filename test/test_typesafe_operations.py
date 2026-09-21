"""Operational contract tests for the TypeSafe boundary."""

import logging
import os
import unittest
from unittest.mock import patch

import httpx

from backend.main import app, get_command_processor
from backend.models import CommandIntent, CommandResult
from backend.typesafe_health import (
    FAILURE_MAPPINGS,
    TypeSafeFailureKind,
    TypeSafeHealth,
    TypeSafeOperationalError,
    map_typesafe_error,
    typesafe_health,
)


class TypeSafeOperationsTests(unittest.TestCase):
    def test_typesafe_failure_mapping(self) -> None:
        for kind, expected in FAILURE_MAPPINGS.items():
            with self.subTest(kind=kind.value):
                self.assertEqual(map_typesafe_error(TypeSafeOperationalError(kind)), expected)

    def test_typesafe_health_transitions_and_recovery(self) -> None:
        state = TypeSafeHealth()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "secret"}):
            self.assertEqual(state.snapshot()["status"], "unverified")
            state.record(success=True, model="jev")
            self.assertEqual(state.snapshot()["status"], "healthy")
            state.record(success=False)
            self.assertEqual(state.snapshot()["status"], "degraded")
            state.record_unavailable()
            self.assertEqual(state.snapshot()["status"], "unavailable")
            state.record(success=True)
            self.assertEqual(state.snapshot()["status"], "healthy")


class TypeSafeEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.old_key = os.environ.get("TYPESAFE_API_KEY")
        os.environ["TYPESAFE_API_KEY"] = "test-api-key"
        typesafe_health.reset()

    async def asyncTearDown(self) -> None:
        if self.old_key is None:
            os.environ.pop("TYPESAFE_API_KEY", None)
        else:
            os.environ["TYPESAFE_API_KEY"] = self.old_key
        app.dependency_overrides.clear()
        typesafe_health.reset()

    @staticmethod
    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def test_typesafe_health_endpoint_is_passive(self) -> None:
        calls = 0

        class Processor:
            async def process(self, *_args):
                nonlocal calls
                calls += 1

        async def dependency():
            return Processor()

        app.dependency_overrides[get_command_processor] = dependency
        async with self.client() as client:
            responses = [await client.get("/api/health/typesafe") for _ in range(3)]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(all(response.json()["status"] == "unverified" for response in responses))
        self.assertEqual(calls, 0)

    async def test_typesafe_missing_configuration_contract(self) -> None:
        from backend.typesafe_health import MissingTypeSafeConfigurationError

        os.environ.pop("TYPESAFE_API_KEY")

        class Processor:
            async def process(self, *_args):
                raise MissingTypeSafeConfigurationError

        async def dependency():
            return Processor()

        app.dependency_overrides[get_command_processor] = dependency
        async with self.client() as client:
            health = await client.get("/api/health/typesafe")
            response = await client.post("/api/game/command", json={"control": "hello"})

        self.assertEqual(health.json()["status"], "unconfigured")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["code"], "typesafe_not_configured")

    async def test_successful_uncertainty_is_healthy_http_success(self) -> None:
        result = CommandResult(
            success=True, message="Please clarify your command.",
            intent=CommandIntent.UNCLEAR, confidence=0.25,
            clarification_required=True,
        )

        class Processor:
            metadata = {"model": "jev-test", "usage": {"input_tokens": 10, "output_tokens": 2}}

            async def process(self, *_args):
                return result

        async def dependency():
            return Processor()

        app.dependency_overrides[get_command_processor] = dependency
        async with self.client() as client:
            response = await client.post("/api/game/command", json={"control": "maybe"})
            health = await client.get("/api/health/typesafe")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["clarification_required"])
        self.assertEqual(health.json()["status"], "healthy")
        self.assertEqual(health.json()["model"], "jev-test")

    async def test_failed_command_updates_health_and_sanitizes_output(self) -> None:
        class Processor:
            async def process(self, *_args):
                raise TypeSafeOperationalError(
                    TypeSafeFailureKind.AUTHENTICATION,
                    request_id="provider-request-id",
                )

        async def dependency():
            return Processor()

        app.dependency_overrides[get_command_processor] = dependency
        with self.assertLogs("backend.main", logging.WARNING) as captured:
            async with self.client() as client:
                response = await client.post(
                    "/api/game/command", json={"control": "raw utterance"}
                )
                health = await client.get("/api/health/typesafe")

        public_text = response.text + " ".join(captured.output)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(health.json()["status"], "unavailable")
        self.assertIn("request_id", response.json()["detail"])
        self.assertNotIn("test-api-key", public_text)
        self.assertNotIn("raw utterance", public_text)
        self.assertNotIn("provider-body", public_text)

    async def test_all_failures_have_observable_http_and_health_mappings(self) -> None:
        for kind, expected in FAILURE_MAPPINGS.items():
            if kind is TypeSafeFailureKind.NOT_CONFIGURED:
                continue

            class Processor:
                async def process(self, *_args, failure_kind=kind):
                    raise TypeSafeOperationalError(failure_kind)

            async def dependency():
                return Processor()

            with self.subTest(kind=kind.value):
                typesafe_health.reset()
                app.dependency_overrides[get_command_processor] = dependency
                async with self.client() as client:
                    response = await client.post(
                        "/api/game/command", json={"control": "test command"}
                    )
                    health = await client.get("/api/health/typesafe")

                self.assertEqual(response.status_code, expected.http_status)
                self.assertEqual(response.json()["detail"]["code"], expected.code)
                self.assertIn("request_id", response.json()["detail"])
                self.assertEqual(health.json()["status"], expected.health_status)

    async def test_jev_adapter_translates_sdk_failures_to_domain_categories(self) -> None:
        from backend.jev_command_interpreter import JevCommandInterpreter
        from typesafe_sdk import (
            TypeSafeAPIConnectionError,
            TypeSafeAPIResponseValidationError,
            TypeSafeAPITimeoutError,
            TypeSafeAuthenticationError,
            TypeSafeBadRequestError,
            TypeSafeInternalServerError,
            TypeSafeNotFoundError,
            TypeSafeRateLimitError,
        )

        cases = (
            (TypeSafeAuthenticationError(401, {}, {}), TypeSafeFailureKind.AUTHENTICATION),
            (TypeSafeAPIConnectionError("offline"), TypeSafeFailureKind.TRANSPORT),
            (TypeSafeAPITimeoutError(5), TypeSafeFailureKind.TIMEOUT),
            (TypeSafeRateLimitError(429, {}, {}), TypeSafeFailureKind.RATE_LIMIT),
            (TypeSafeInternalServerError(503, {}, {}), TypeSafeFailureKind.OVERLOAD),
            (TypeSafeInternalServerError(500, {}, {}), TypeSafeFailureKind.SERVICE_UNAVAILABLE),
            (TypeSafeNotFoundError(404, {}, {}), TypeSafeFailureKind.SERVICE_UNAVAILABLE),
            (TypeSafeBadRequestError(400, {}, {}), TypeSafeFailureKind.BAD_REQUEST),
            (TypeSafeAPIResponseValidationError(200, {}, {}, "answers.intent"), TypeSafeFailureKind.MALFORMED_RESPONSE),
        )

        for sdk_error, expected_kind in cases:
            class Client:
                async def system_one(self, **_kwargs):
                    raise sdk_error

            with self.subTest(error=type(sdk_error).__name__):
                with self.assertRaises(TypeSafeOperationalError) as raised:
                    await JevCommandInterpreter(Client()).interpret("hello", None)
                self.assertEqual(raised.exception.kind, expected_kind)


if __name__ == "__main__":
    unittest.main()
