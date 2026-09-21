# Voice Tic-Tac-Toe

Voice-controlled tic-tac-toe with a FastAPI game backend, TypeSafe Jev natural-language controls, local Qwen ASR, and local Kokoro TTS.

## Run

Install dependencies with `uv sync` (or `uv pip install -r requirements.txt`), download the retained speech models with `./download_models.sh`, then start the backend with `./voice_game.sh start`. The browser is served at `http://localhost:8002`.

Natural-language controls use `POST /api/game/command` and require `TYPESAFE_API_KEY`. Structured game controls remain usable without that credential. The standalone client (`voice_tic_tac_toe.py`) sends transcripts to the same endpoint.

## Verification

```bash
uv run pytest -q
uv run python scripts/evaluate_jev_fixtures.py
```

The fixture evaluator requires a TypeSafe credential and network access; deterministic tests use the fake command boundary.
