# Inspection and departure

Players inspect the shared board and current turn, or leave without interpretation.

## Sub-features

- `inspect-board` shows the current board without placing a mark.
- `inspect-status` shows the current turn or result.
- `depart` returns a goodbye response and clears Pending Commands.

## How to get to it (user POV)

On `/` or `/index.html`, choose Show Board, Check Status, or Quit. Typed `show board`, `check status`, and `goodbye` provide Natural-Language Controls for these intentions. The regular page displays the board and status but has no quick inspection or Quit buttons.

## Driving it with Playwright

Preconditions: healthy isolated backend and an ongoing game with at least one mark. Typed paths also need provider credentials.

- Record GET `/api/game`, then click `page.locator('[data-cmd="show_board"]').click()` and `page.locator('[data-cmd="check_status"]').click()`. Wait for GET `/api/game` and require visible board and turn matching the initial state, with no mutation.
- Click `page.locator('[data-cmd="quit"]').click()`. Wait for POST `/api/game/depart`. Require `Thanks for playing! Goodbye!` in `#voice-messages` and the response body. Departure retains the board; verify that GET `/api/game` still matches.
- For typed entry points, use `#voice-input` and `#send-cmd-btn` with each phrase and capture the `/api/game/command` response. Establish a pending move first, depart, then send `center`. Inspect the follow-up response to prove the earlier Pending Command was cleared rather than assuming it from the goodbye text.

## Gotchas

Inspection before a game produces an error rather than creating one. Quit does not delete the game. A browser still sees retained game state after departure. Structured quick buttons bypass Jev.
