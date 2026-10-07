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
def debug_server(enabled):
    class DelayedProvider(RecordingTypeSafeClient):
        async def system_one(self, *, state, questions):
            await asyncio.sleep(.4)
            return await super().system_one(state=state, questions=questions)

    provider = DelayedProvider(intent="start_game")
    session = GameSession()
    processor = PlayerCommandProcessor(JevCommandInterpreter(provider), session)
    app.dependency_overrides[get_command_processor] = lambda: processor
    with socket.socket() as allocation:
        allocation.bind(("127.0.0.1", 0))
        port = allocation.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="error"))
    thread = threading.Thread(target=server.run)
    with patch.dict(os.environ, {"JEV_DEBUG": str(enabled).lower()}), patch("backend.main.get_game_session", return_value=session):
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
