"""Browser acceptance at the real command HTTP and recording provider seams."""

from contextlib import contextmanager
import asyncio
import os
import socket
import threading
import time
from unittest.mock import patch

from playwright.sync_api import sync_playwright
import uvicorn

from backend.game_session import GameSession
from backend.jev_command_interpreter import JevCommandInterpreter
from backend.main import app, get_command_processor
from backend.player_command import PlayerCommandProcessor
from test.test_jev_command_interpreter import RecordingTypeSafeClient


@contextmanager
def debug_server(enabled, provider=None):
    class DelayedProvider(RecordingTypeSafeClient):
        async def system_one(self, *, state, questions):
            await asyncio.sleep(.4)
            return await super().system_one(state=state, questions=questions)

    provider = provider or DelayedProvider(intent="start_game")
    processor = PlayerCommandProcessor(JevCommandInterpreter(provider), GameSession())
    app.dependency_overrides[get_command_processor] = lambda: processor
    with socket.socket() as allocation:
        allocation.bind(("127.0.0.1", 0))
        port = allocation.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="error"))
    thread = threading.Thread(target=server.run)
    with patch.dict(os.environ, {"JEV_DEBUG": str(enabled).lower()}):
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline
                time.sleep(.02)
            yield f"http://127.0.0.1:{port}", provider
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            app.dependency_overrides.clear()
            assert not thread.is_alive()


def test_browser_inspects_actual_exchange_and_disabled_explanation():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            with debug_server(True) as (base, provider):
                page = browser.new_page()
                # Speech is an unrelated external model boundary in this deterministic test.
                page.route("**/api/health/asr", lambda route: route.fulfill(json={"status": "unavailable"}))
                page.route("**/api/health/tts", lambda route: route.fulfill(json={"status": "unavailable"}))
                page.route("**/api/voice/synthesize", lambda route: route.fulfill(status=503, json={"detail": "disabled in browser contract"}))
                page.goto(base + "/index.html")
                panel = page.locator("#jev-debug-panel")
                assert not panel.is_visible()
                page.locator("#jev-debug-button").click()
                assert panel.is_visible()
                page.wait_for_function("document.querySelector('#jev-debug-panel > p').hidden")
                page.locator("#voice-input").fill("<img src=x onerror=alert(1)> start")
                with page.expect_response(lambda response: response.url.endswith("/api/game/command")) as result:
                    page.locator("#send-cmd-btn").click()
                    assert "pending" in panel.locator(".jev-exchange-entry").inner_text()
                assert result.value.status == 200
                page.locator(".jev-exchange-entry").filter(has_text="success").wait_for()
                assert "Jev: success" in panel.inner_text()
                assert "Application: start_game, accepted" in panel.inner_text()
                assert panel.locator("img").count() == 0
                panel.locator("summary").filter(has_text="Full request").click()
                assert "state_change_requested" in panel.inner_text()
                assert "<img src=x onerror=alert(1)> start" in panel.inner_text()
                assert len(provider.calls) == 1
                page.locator("#jev-debug-button").click()
                assert not panel.is_visible()
                page.close()
            with debug_server(False) as (base, provider):
                page = browser.new_page()
                page.goto(base + "/regular_game.html")
                page.locator("#jev-debug-button").click()
                assert "JEV_DEBUG=true" in page.locator("#jev-debug-panel").inner_text()
                assert len(provider.calls) == 0
                page.close()
        finally:
            browser.close()


def test_browser_distinguishes_application_outcomes_from_provider_failure():
    from typesafe_sdk import TypeSafeAuthenticationError

    class OutcomeProvider(RecordingTypeSafeClient):
        async def system_one(self, *, state, questions):
            await asyncio.sleep(.1)
            if state["natural_language_control"] == "provider failure":
                raise TypeSafeAuthenticationError(401, {"message": "Authorization: Bearer private-key"}, {})
            return await super().system_one(state=state, questions=questions)

    provider = OutcomeProvider(intent="start_game", presence=1, uniqueness=1)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            with debug_server(True, provider) as (base, _):
                page = browser.new_page()
                for path in ["health/asr", "health/tts", "voice/synthesize"]:
                    page.route("**/api/" + path, lambda route: route.fulfill(status=503, json={"detail": "external speech disabled"}))
                page.goto(base + "/index.html")
                page.locator("#jev-debug-button").click()
                page.wait_for_function("document.querySelector('#jev-debug-panel > p').hidden")
                panel = page.locator("#jev-debug-panel")

                def submit(control):
                    page.locator("#voice-input").fill(control)
                    with page.expect_response(lambda response: response.url.endswith("/api/game/command")) as response:
                        page.locator("#send-cmd-btn").click()
                    page.locator(".jev-exchange-entry").filter(has_text=control).click()
                    return response.value

                submit("start game")
                provider.intent = "place_move"
                submit("play center")
                rejection = submit("play center again")
                assert rejection.status == 200
                assert rejection.json()["success"]
                assert rejection.json()["jev_exchange"]["application"]["outcome"] == "rejected"
                assert "Jev: success" in panel.inner_text()
                assert "Application: place_move, rejected" in panel.inner_text()
                assert rejection.json()["message"] in panel.inner_text()
                page.route("**/api/game", lambda route: route.abort())
                provider.intent = "start_game"
                refreshed = submit("restart with failed refresh")
                assert refreshed.status == 200
                page.wait_for_function("document.querySelector('#voice-history')?.textContent.includes('Error:') || document.body.textContent.includes('Error: Failed to fetch')")
                assert "Jev: success" in panel.inner_text()
                page.unroute("**/api/game")
                provider.intent = "place_move"
                provider.uniqueness = 0
                clarification = submit("play somewhere")
                assert clarification.json()["clarification_required"]
                assert "Jev: success" in panel.inner_text()
                assert "Application: place_move, clarification" in panel.inner_text()
                assert clarification.json()["message"] in panel.inner_text()
                failure = submit("provider failure")
                assert failure.status == 401
                assert "Jev: failure" in panel.inner_text()
                assert "typesafe_authentication_failed" in panel.inner_text()
                panel.locator("summary").filter(has_text="Full request").click()
                assert "provider failure" in panel.inner_text()
                assert "private-key" not in panel.inner_text()
                assert "Authorization" not in panel.inner_text()
                assert "Application:" not in panel.inner_text()
                assert "ms" in panel.locator(".jev-exchange-entry").first.inner_text()
                page.close()
        finally:
            browser.close()
