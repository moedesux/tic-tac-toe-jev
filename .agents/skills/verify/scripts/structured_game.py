#!/usr/bin/env python3
"""Drive a disposable real backend through browser Structured Controls."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[4]
    evidence = Path(sys.argv[1]).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    actions = []
    environment = os.environ.copy()
    environment.pop("TYPESAFE_API_KEY", None)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (evidence / "backend.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Owned backend exited; inspect backend.log")
                if f"Uvicorn running on {base}" not in (evidence / "backend.log").read_text():
                    time.sleep(0.1)
                    continue
                try:
                    with urlopen(base + "/api/health", timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("Backend readiness timed out")
            assert server.poll() is None, "Owned backend exited during readiness"
            with urlopen(base + "/api/health/typesafe", timeout=5) as response:
                provider = json.load(response)
            assert server.poll() is None, "Owned backend exited during doctor"
            assert health["status"] == "healthy", health
            assert health["service"] == "Tic-Tac-Toe API" and health["version"] == "1.0.0", health
            assert provider["status"] == "unconfigured", provider
            doctor = {"feature": "structured-win", "entry_point": "/regular_game.html", "url": base, "pid": server.pid, "health": health, "typesafe": provider}
            (evidence / "doctor.json").write_text(json.dumps(doctor, indent=2))
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    context = browser.new_context()
                    context.tracing.start(screenshots=True, snapshots=True, sources=True)
                    page = context.new_page()
                    try:
                        page.goto(base + "/regular_game.html")
                        expect(page.locator("#new-game-btn")).to_be_visible()
                        page.screenshot(path=str(evidence / "before.png"), full_page=True)
                        actions.append({"action": "click", "selector": "#new-game-btn"})
                        with page.expect_response(lambda r: r.url == base + "/api/game" and r.request.method == "POST") as created:
                            page.locator("#new-game-btn").click()
                        assert created.value.status == 200
                        initial = created.value.json()
                        assert initial["board"] == [None] * 9 and initial["turn"] == "X", initial
                        for position, mark in [(0, "X"), (3, "O"), (1, "X"), (4, "O"), (2, "X")]:
                            selector = f'#game-board [data-position="{position}"]'
                            actions.append({"action": "click", "selector": selector, "expected": mark})
                            with page.expect_response(lambda r: r.url == base + "/api/game/move" and r.request.method == "POST") as moved:
                                page.locator(selector).click()
                            assert moved.value.status == 200
                            expect(page.locator(selector)).to_have_text(mark)
                        expect(page.locator("#status")).to_have_text("X Wins!")
                        state_response = context.request.get(base + "/api/game")
                        assert state_response.status == 200
                        state = state_response.json()
                        assert state["board"] == ["X", "X", "X", "O", "O", None, None, None, None], state
                        assert state["winner"] == "X" and state["gameOver"] and state["status"] == "completed", state
                        assert state["gameId"] == initial["gameId"]
                        (evidence / "state.json").write_text(json.dumps(state, indent=2))
                        (evidence / "page.txt").write_text(page.locator("body").inner_text())
                        page.screenshot(path=str(evidence / "after.png"), full_page=True)
                    finally:
                        (evidence / "actions.json").write_text(json.dumps(actions, indent=2))
                        context.tracing.stop(path=str(evidence / "trace.zip"))
                finally:
                    browser.close()
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
            (evidence / "cleanup.json").write_text(json.dumps({"pid": server.pid, "exit_code": server.returncode}))
    assert all((evidence / name).is_file() for name in ["doctor.json", "actions.json", "state.json", "before.png", "after.png", "trace.zip", "cleanup.json"])
    print(f"Verified browser Structured Control game. Evidence retained at {evidence}")
