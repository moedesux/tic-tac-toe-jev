# Voice tic-tac-toe verification map

Start with a new isolated backend and doctor from [verify](../SKILL.md). Each process has one shared game. Every browser and standalone client connected to that process changes that same game. Baseline needs no credentials. Its new-game announcement attempts TTS, so report that outcome separately from gameplay. Keep integration prerequisites and skipped entry points explicit.

- [Structured gameplay](structured-game.md) covers starting, alternating turns, invalid moves, wins, draws, and restart.
- [Natural-Language Controls](player-commands.md) covers typed commands and Pending Commands.
- [Inspection and departure](inspection-departure.md) covers board, status, and Quit.
- [Speech and standalone client](speech.md) covers browser microphone, audible responses, and standalone simulation.

Use stable selectors and production endpoints. Capture browser actions, resulting DOM, and GET `/api/game` for game mutations. Capture response bodies for commands and speech errors. Keep evidence after cleanup. A proof of one entry point does not cover the others. The initial helper proves `structured-win` through `/regular_game.html`.
