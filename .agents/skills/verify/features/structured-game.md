# Structured gameplay

Players start a shared game and alternate X and O marks through explicit controls.

## Sub-features

- `structured-start` starts an empty board with X to move.
- `structured-turns` alternates marks and rejects occupied cells.
- `structured-win` completes a winning row and stops further moves.
- `structured-draw` fills the board without a winner.
- `structured-restart` clears a completed or ongoing game.

## How to get to it (user POV)

Open `/`, `/index.html`, or `/regular_game.html` and choose New Game, then board cells. On the full page, Start Game and the nine named position buttons are additional entry points.

## Driving it with Playwright

Preconditions: an isolated healthy backend. Full pages also poll local speech services.

- Start with `page.locator("#new-game-btn").click()` or `page.locator('[data-cmd="start_game"]').click()`. Wait for POST `/api/game`. Assert nine empty cells and `Current turn: X`.
- Move with `page.locator('#game-board [data-position="0"]').click()` or `page.locator('.position-buttons [data-row="0"][data-col="0"]').click()`. Wait for POST `/api/game/move`. Assert X in cell zero and O next. Repeat an occupied move and require HTTP 400 with unchanged GET `/api/game` state.
- Win through cells 0, 3, 1, 4, 2. Run `uv run .agents/skills/verify/scripts/structured_game.py /tmp/tic-tac-toe-proof-NEW` for this entry point. Require `X Wins!`, three winning cells, `winner == "X"`, and `gameOver == true`. Click an empty board cell afterward and confirm state stays unchanged.
- Draw through cells 0, 1, 2, 4, 3, 5, 7, 6, 8. Require `It's a Draw!`, `status == "draw"`, `winner == null`, and nine occupied cells.
- Restart with New Game. Require an empty board, X turn, ongoing status, and a new `gameId`. Capture the prior and replacement state.

## Gotchas

Cells exist only after starting a game. Data positions are zero-based. Board cells ignore clicks after completion; named position buttons can surface an API error instead. Starting a game automatically requests TTS even on the regular page. Record synthesis success or failure separately from the game result. There is no automated opponent. The shipped proof does not exercise the full page or named position buttons.
