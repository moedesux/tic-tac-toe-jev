---
name: verify
description: Verify Voice tic-tac-toe through its real browser controls, typed Player Commands, HTTP state, and standalone client. Use after changes to gameplay, pending dialogue, browser controls, or speech integration.
---

# Verify Voice tic-tac-toe

Read [the feature index](features/README.md) and select the entry points relevant to the change. Run from the repository root. The primary surface is the browser. HTTP provides a second view of authoritative game state. The standalone microphone client is an additional surface.

## Launch

Run `uv run python scripts/check_dev_environment.py`. Preserve existing worktree changes.

The baseline helper needs Playwright in the repository environment and Chromium. Check with `uv run python -c 'import playwright.sync_api'`. If absent, install verification tooling with `uv pip install playwright` and `uv run playwright install chromium`. This adds tooling to the environment, without changing production dependencies.

Run the complete baseline with a new evidence directory:

```bash
uv run .agents/skills/verify/scripts/structured_game.py /tmp/tic-tac-toe-proof-$(date +%Y%m%d-%H%M%S)
```

The helper starts `python -m uvicorn backend.main:app --host 127.0.0.1 --port PORT` using the current `uv` Python, an available ephemeral port, and repository working directory. It waits up to 60 seconds for `/api/health`. It removes `TYPESAFE_API_KEY` from its child environment to verify Structured Controls without provider usage. It terminates its own child in `finally`, including failed runs.

For other mapped features, use the same launch command with a free port and hold the child process handle until cleanup. Use one worker. Set the browser URL to that port. Load credentials using `uv run --env-file .env python -m uvicorn backend.main:app --host 127.0.0.1 --port PORT` only for live Natural-Language Controls. Choose PORT by binding a temporary socket to port zero as the helper does. A port allocation race must fail the run if the child exits; never adopt another server on that port.

Every backend process owns one shared game, with no per-browser sessions or persisted game database. Separate ports and processes isolate games. Speech assets and config remain shared and read-only. Speech runs can compete for GPU or audio devices, so run those serially. Do not use `voice_game.sh` for verification because it manages the user's shared `.backend.pid` and backend log.

## Doctor

Check that your child is alive, then GET `/api/health` on its exact URL. Require `status == "healthy"`, `service == "Tic-Tac-Toe API"`, and `version == "1.0.0"` for the current config. Repeat the liveness check after readiness. This passive check uses the instance just launched from the working tree, not a preexisting deployment. The helper records the URL, PID, health response, and passive `/api/health/typesafe` response in `doctor.json`. A baseline run requires TypeSafe `unconfigured`.

When driving looks wrong, repeat doctor first and inspect the owned backend log. ASR and TTS health routes can load models; they are not passive doctor checks. TypeSafe `unverified` means configured but no successful provider request yet.

## Drive

Use Playwright's synchronous Python API from the repository environment. The shipped helper clicks `#new-game-btn`, then `#game-board [data-position="0"]`, `3`, `1`, `4`, and `2` on `/regular_game.html`. It asserts `#status` reads `X Wins!` and verifies the final board through GET `/api/game`.

For additional recipes, create a browser context and use `page.goto(base + path)`, `page.locator(selector).click()`, `fill()`, or `press("Enter")`. Wait for the matching production HTTP response around each action with `page.expect_response`, then assert its result and the DOM. Use `context.request.get(base + "/api/game")` for read-only state evidence. Do not call frontend functions or internal session setters to arrange a game.

The baseline uses the regular page because `/` and `/index.html` poll speech health and may load models even with the speech toggle off. The regular page still requests new-game announcement synthesis and has no speech toggle. That request can load TTS assets; inspect its response in the trace and backend log. A synthesis error does not invalidate an otherwise correct Structured Control game, but must be reported separately. Run full pages as a separate integration path. Do not intercept requests or replace production dependencies to label the whole page verified.

## Evidence

Keep each run in its explicitly named evidence directory outside the worktree. The helper writes `backend.log`, `doctor.json`, `actions.json`, `before.png`, `after.png`, `page.txt`, `state.json`, `trace.zip`, and `cleanup.json`. A failed run retains whatever artifacts it reached. Open a trace with `uv run playwright show-trace /tmp/RUN/trace.zip`, replacing RUN with the actual recorded directory.

Proof must include the action and resulting visible state, plus authoritative HTTP state for mutations. Record the mapped feature ID and entry point in any additional transcript. Capture production response status and body for command clarification and errors. Never capture credentials or dump environment variables. No mocks are used by this driver. Deterministic tests isolate provider and speech boundaries, but their results are separate from live integration proof.

Baseline skips Natural-Language Controls, microphone capture, transcription, and external provider calls. Its actions contain browser Structured Controls on the regular page, including an automatic new-game announcement synthesis request. Inspect the trace and backend log to confirm the actual request paths and synthesis outcome. Do not claim audible playback from a headless run. Simulation skips microphone recording and ASR but still loads TTS and can play audio; it is not a dry run.

## Cleanup

Close browser contexts and browsers. Terminate and wait for the exact backend child you started; kill that child only if graceful termination times out. Never kill by process name or invoke the shared stop script. The helper records the child exit code in `cleanup.json`. Game state disappears with the process. Keep evidence and existing model assets. Confirm the named proof files still exist after teardown. On failure, cleanup comes before any retry and the retry uses a new evidence directory.

## Helpers

`scripts/structured_game.py` is executable. Its required argument is a new evidence-directory path. It owns launch, doctor, one browser game, evidence, and cleanup. Exit code zero means all assertions passed. This proves the regular-page entry point only; use the feature map to select the other affected paths.
