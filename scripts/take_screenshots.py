#!/usr/bin/env python3
"""
Screenshot generator for the Voice Tic-Tac-Toe game page.

Uses Playwright to capture three game states:

  1. Landing page (empty board, no game)
  2. In-progress game (commands routed through /api/game/command → Jev)
  3. Win state (built via direct frontend makeMove() calls for guaranteed positions)

Servers assumed running:
    Backend:  http://localhost:8002

Usage:
    python scripts/take_screenshots.py
"""

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:8002"
SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "screenshots"
VIEWPORT = {"width": 1280, "height": 800}
INDEX_URL = f"{BASE_URL}/index.html"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    """Print a timestamped log message."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def take_shot(page: Page, filename: str) -> Path:
    """Take a full-page screenshot and return the saved Path."""
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=True)
    log(f"  Saved -> {path}")
    return path


def wait_for_bot_message(page: Page, max_wait_ms: int = 45000) -> bool:
    """Wait for the Jev to respond after a Send click.

    Polls every 500 ms until one of these conditions is met:
      - A new ``.message.bot`` appears inside ``#voice-messages``
      - The board state changes (GET /api/game returns updated board)

    Returns ``True`` if a response was detected, ``False`` on timeout.
    """
    start = time.time()
    initial_bot_count = len(page.query_selector_all("#voice-messages .message.bot"))
    initial_board = page.evaluate(
        "fetch('/api/game').then(r => r.json()).then(d => d.board)"
    )

    log(f"    Initial bot messages: {initial_bot_count}")
    log(f"    Initial board: {initial_board}")

    poll_interval = 0.5
    api_poll_interval = 1.0
    last_api_poll = 0.0

    while (time.time() - start) * 1000 < max_wait_ms:
        time.sleep(poll_interval)
        elapsed = (time.time() - start) * 1000

        # Check for new bot message
        current_bot_count = len(page.query_selector_all("#voice-messages .message.bot"))
        if current_bot_count > initial_bot_count:
            log(f"    Bot message detected after {elapsed:.0f}ms ({current_bot_count} total)")
            return True

        # Check for board state change via API (throttled to every 1s)
        now = time.time()
        if now - last_api_poll >= api_poll_interval:
            last_api_poll = now
            try:
                board = page.evaluate(
                    "fetch('/api/game').then(r => r.json()).then(d => d.board)"
                )
                if board is not None and board != initial_board:
                    log(f"    Board state changed after {elapsed:.0f}ms")
                    return True
            except Exception:
                pass  # API not ready yet

    log(f"    Timed out after {max_wait_ms}ms (bot count: {initial_bot_count})")
    return False


def send_command(page: Page, text: str, max_wait_ms: int = 45000) -> bool:
    """Type a command, click Send, and wait for the bot response.

    Returns ``True`` on success, ``False`` on timeout.
    """
    log(f"    Typing: \"{text}\"")
    page.fill("#voice-input", text)
    with page.expect_response(lambda r: r.url.endswith("/api/game/command"), timeout=max_wait_ms) as pending:
        page.click("#send-cmd-btn")
    response = pending.value
    if not response.ok:
        raise RuntimeError(f"Command returned HTTP {response.status}")
    page.wait_for_function("document.querySelectorAll('#voice-messages .message.bot').length > 0")
    return True


def navigate_and_wait(page: Page) -> None:
    """Navigate to the Voice Game page and wait for network idle + settle."""
    log("  Navigating to Voice Game page...")
    page.goto(INDEX_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    log("  Page loaded")

# ---------------------------------------------------------------------------
# Scenario 1 — Landing
# ---------------------------------------------------------------------------


def screenshot_01_landing(page: Page) -> Path:
    """01 — Voice game landing page (empty board, no game)."""
    log("Taking screenshot: 01-voice-game-landing (Voice Game, no game yet)")
    navigate_and_wait(page)
    return take_shot(page, "01-voice-game-landing.png")

# ---------------------------------------------------------------------------
# Scenario 2 — In Progress (Jev interaction flow)
# ---------------------------------------------------------------------------


def screenshot_02_in_progress(page: Page) -> Path:
    """02 — Voice game with Jev interaction.

    Flow:
      1. "start game"        → creates a new game
      2. "place at center"   → X at {row:1, col:1}
      3. Verify at least 2 bot messages in chat
    """
    log("Taking screenshot: 02-voice-game-in-progress (Jev interaction flow)")
    navigate_and_wait(page)

    # --- Command 1: start game ---
    log("  Sending command: start game")
    if not send_command(page, "start game", max_wait_ms=45000):
        log("    ERROR: start game timed out")

    # --- Command 2: place at center ---
    log("  Sending command: place at center")
    if not send_command(page, "place at center", max_wait_ms=45000):
        log("    ERROR: place at center timed out")

    # --- Verify at least 2 bot messages ---
    bot_messages = page.query_selector_all("#voice-messages .message.bot")
    log(f"  Bot messages in chat: {len(bot_messages)}")
    if len(bot_messages) < 2:
        raise RuntimeError("Expected at least two command responses")

    # Brief pause so any animations settle
    page.wait_for_timeout(500)
    return take_shot(page, "02-voice-game-in-progress.png")

# ---------------------------------------------------------------------------
# Scenario 3 — Win (direct frontend calls for guaranteed positions)
# ---------------------------------------------------------------------------


def screenshot_03_win(page: Page) -> Path:
    """03 — Voice game showing a win state.

    Uses direct frontend makeMove() calls to guarantee exact positions.
    This avoids Jev non-determinism — we need a reliable win.

    Move sequence (top-row win for X):
      1. makeMove(0)  → X at top-left (position 0)
      2. makeMove(3)  → O at middle-left (position 3)
      3. makeMove(1)  → X at top-center (position 1)
      4. makeMove(4)  → O at center (position 4)
      5. makeMove(2)  → X at top-right (position 2) — ROW WIN (0,1,2)
    """
    log("Taking screenshot: 03-voice-game-win (real win via direct frontend calls)")
    navigate_and_wait(page)

    # --- Create a new game ---
    log("  Clicking New Game button...")
    page.click("#new-game-btn")
    page.wait_for_timeout(1000)
    log("  Game created, board should be rendered")

    # --- Place moves via direct frontend calls (guarantees exact positions) ---

    log("  Placing X at top-left (position 0)...")
    page.evaluate("makeMove(0)")
    page.wait_for_timeout(1000)

    log("  Placing O at middle-left (position 3)...")
    page.evaluate("makeMove(3)")
    page.wait_for_timeout(1000)

    log("  Placing X at top-center (position 1)...")
    page.evaluate("makeMove(1)")
    page.wait_for_timeout(1000)

    log("  Placing O at center (position 4)...")
    page.evaluate("makeMove(4)")
    page.wait_for_timeout(1000)

    log("  Placing X at top-right (position 2) — completes top-row win...")
    page.evaluate("makeMove(2)")
    page.wait_for_timeout(1000)

    # --- Verify win state ---
    game_over = page.evaluate("currentGameData?.gameOver")
    winner = page.evaluate("currentGameData?.winner")
    log(f"  Game over: {game_over}, Winner: {winner}")

    if not game_over:
        raise RuntimeError("Expected a completed game")
    elif winner != "X":
        log(f"    WARNING: Expected winner 'X', got '{winner}'")

    # Extra pause for win highlight animation to render
    page.wait_for_timeout(1000)
    return take_shot(page, "03-voice-game-win.png")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    log("=" * 60)
    log("Voice Tic-Tac-Toe Screenshot Generator")
    log("=" * 60)

    # Create output directory
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Screenshot directory: {SCREENSHOT_DIR.resolve()}")

    scenarios = [
        ("Voice Game — Landing", screenshot_01_landing),
        ("Voice Game — In Progress", screenshot_02_in_progress),
        ("Voice Game — Win", screenshot_03_win),
    ]

    browser = None
    context = None
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport=VIEWPORT,
                ignore_https_errors=True,
            )
            page = context.new_page()

            for name, fn in scenarios:
                log(f"\n--- {name} ---")
                try:
                    fn(page)
                except Exception as exc:
                    log(f"ERROR in '{name}': {exc}")
                    return 1

            context.close()
            browser.close()

    except Exception as exc:
        log(f"FATAL: Failed to launch browser: {exc}")
        return 1

    # Summary
    files = sorted(SCREENSHOT_DIR.glob("*.png"))
    log("\n" + "=" * 60)
    log(f"Done! {len(files)} screenshot(s) saved to {SCREENSHOT_DIR.resolve()}:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        log(f"  {f.name} ({size_kb:.0f} KB)")
    log("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
