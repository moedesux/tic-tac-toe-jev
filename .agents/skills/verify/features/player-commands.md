# Natural-Language Controls

Players type commands and supply follow-ups to finish a Pending Command.

## Sub-features

- `command-send` interprets typed language through Send and Enter.
- `command-pending` asks for a missing position and completes on a follow-up.
- `command-cancel` cancels pending dialogue without placing a mark.
- `command-unconfigured` reports missing provider configuration.

## How to get to it (user POV)

Open `/` or `/index.html`, type into the command field, then choose Send or press Enter. Browser speech transcripts and standalone client transcripts reach the same command endpoint, with their input paths covered in the speech map.

## Driving it with Playwright

Preconditions: isolated backend with `TYPESAFE_API_KEY` loaded for live success. Uncheck `#tts-toggle` to silence responses; full-page health polling can still load models.

- Use `page.locator("#voice-input").fill("start a game")` and `page.locator("#send-cmd-btn").click()` inside `page.expect_response` for POST `/api/game/command`. Require a successful result and an empty ongoing board in GET `/api/game`.
- Fill `place a mark` and use `page.locator("#voice-input").press("Enter")`. Require `clarification_required == true`, a pending move with missing position, and an unchanged board.
- Fill `center` and choose Send. Require pending state cleared in the response and X at board index four in both DOM and GET `/api/game`.
- Start another missing-position request, then send `cancel`. Require pending state cleared and unchanged board. Preserve both command responses as evidence.
- On an explicitly unconfigured backend, send `start a game`. Require HTTP 503 with a configuration error and visible error feedback. Check Structured Controls still work separately.

## Gotchas

Live interpretation can clarify rather than execute. Record the actual response instead of assuming a phrase guarantees an intent. Confidence and legality are application policy. Read `docs/acceptance-test-matrix.md` for exhaustive pending-state branches. Passive TypeSafe health should become healthy after successful live commands. Never substitute a fake interpreter in a live proof.
