# Jev Command Interpretation Migration

## Outcome

Replace the self-hosted generative command interpreter with TypeSafe Jev while retaining local speech recognition, local speech synthesis, the existing shared X/O game, and both browser and standalone voice entry points. Application code owns game rules, state transitions, dialogue state, uncertainty policy, and response text. Jev supplies bounded typed judgments about natural-language commands.

Production has one inference path and no compatibility flag. Historical Git commits remain unchanged. The architecture decision record is the only current file allowed to name retired technologies.

## Command interpretation

One Jev request evaluates structured state containing:

- the current utterance;
- the board, current mark, and game status;
- an optional pending command.

The request batches independent judgments:

- a Choice among greeting, start game, show board, place move, show status, thanks, goodbye, and unclear;
- a Noul indicating whether a position was stated;
- a Choice among the nine board positions;
- a Noul detecting an initial move requested with a new game;
- when applicable, Nouls for pending-command cancellation, affirmation, and rejection.

The board allows uniquely identifying relative references. Jev reports the intended position even when it is occupied; deterministic game code remains authoritative for legality. It never chooses a strategic move for a player.

## Dialogue behavior

There is no rolling transcript or provider-shaped message history. The backend stores an explicit pending command alongside the one shared game session.

A pending command may:

- lack a position; or
- hold a proposed position awaiting confirmation.

It is cleared by completion, cancellation, a confident replacement command, a new game, game completion, or departure. An unclear follow-up does not clear it. Social commands leave it intact.

Commands normally execute one action. The only compound behavior is starting a game and placing its requested initial move. If that move lacks a precise position, the game starts and the move becomes pending. Other compounds are clarified and handled one action at a time.

## Confidence policy

Use separate gates for:

- read-only and social commands;
- state-changing moves;
- resetting an existing game;
- position selection.

High-confidence judgments execute. Medium-confidence state changes become pending confirmations. Low-confidence judgments clarify without acting. Actual thresholds are selected from live Jev evaluation results rather than copied from documentation.

## Module design

Create a deep asynchronous command module with a small `process` interface. It hides question construction, Jev result translation, confidence policy, pending transitions, command execution, and deterministic response construction.

Place an internal command-interpreter seam behind that module:

- a Jev adapter uses `AsyncTypeSafeClient` in production;
- a deterministic fake adapter supports automated tests.

Only domain interpretation types cross the seam. TypeSafe SDK response objects remain inside the Jev adapter.

FastAPI owns the TypeSafe client for its application lifetime. The command module invokes in-process game operations; it never calls the application's own HTTP routes. The standalone microphone program is a separate process and therefore uses a small backend HTTP adapter.

## HTTP interface

Replace `POST /api/voice/command` with `POST /api/game/command`. A successful response has domain fields:

```json
{
  "success": true,
  "message": "You placed your mark at middle right.",
  "intent": "place_move",
  "position": "middle_right",
  "confidence": 0.94,
  "clarification_required": false
}
```

For the bounded start-plus-move composition, `intent` remains `start_game` and `position` identifies the applied initial move.

Transport, exhausted rate limiting, missing credentials, and unavailable-model failures return non-success HTTP statuses. Successful uncertain judgments return HTTP 200 with `clarification_required: true`. Structured buttons call game operations directly and remain usable when TypeSafe is unavailable.

`GET /api/health/typesafe` performs no external call. It reports missing configuration or the cached outcome of real command requests: configured/unverified, healthy, degraded, or unavailable. Frontend polling therefore consumes no TypeSafe usage.

## Configuration

Use server environment variables:

- `TYPESAFE_API_KEY`;
- `TYPESAFE_DEFAULT_MODEL`.

Evaluate with the current alias, then pin the validated model version for production. Secrets never enter committed configuration, frontend code, responses, or logs.

## File migration

| Area | Change |
| --- | --- |
| `backend/main.py` | Replace orchestrator initialization and voice command route; own the async client lifecycle, shared game session, pending state, command route, passive TypeSafe health, and error mapping. |
| `backend/game.py` | Retain pure rules; expose in-process operations needed by REST and command handling without adding inference concerns. |
| `backend/models.py` | Add domain command request/response and pending-state models; remove provider-shaped vocabulary. |
| New backend command module | Implement the deep command-processing interface and domain policy. |
| New Jev adapter | Build TypeSafe questions and translate SDK answers into domain interpretations. |
| `voice_game_orchestrator.py` | Delete. |
| `voice_game_interface.py` | Delete; replace only the standalone caller's legitimate HTTP needs with a small backend adapter. |
| `voice_tic_tac_toe.py` | Remove model client arguments and local inference; send transcripts to `/api/game/command`. |
| `config/voice.conf` | Remove the inference-server section; retain ASR, TTS, backend, and audio configuration. |
| `config/config.py` | Remove inference-server properties and retired game-prompt imports. |
| `config/voice_game_config.py` | Remove prompts, tool schemas, slot metadata, and history-oriented settings; relocate the small amount of surviving domain copy or position vocabulary to its owning module. |
| `voice_game.sh` | Remove the inference server process, port, health check, PID file, logs, startup, shutdown, status, and model-path handling. |
| `download_models.sh` | Download and verify only the retained ASR and TTS models. |
| `requirements.txt` | Remove the OpenAI client and add the supported TypeSafe Python SDK; retain other dependencies only where still imported. |
| `frontend/static/app.js` | Use the new command route and response shape, bypass Jev for structured controls, replace the health badge, and handle non-success statuses. |
| `frontend/index.html` | Rename inference health/status wording. |
| Old model-call tests | Delete and replace with command-module tests through the fake adapter. |
| Integration tests | Exercise pending state, confidence behavior, start-plus-move, board-relative language, failure mapping, and both entry points. |
| `data/*.jsonl` and training generator | Delete. Preserve only curated provider-neutral behavior fixtures. |
| `README.md`, `AGENTS.md` | Rewrite commands, setup, architecture, troubleshooting, logs, dependencies, and terminology. |
| `architecture.drawio`, rendered image | Redraw around the Jev adapter and deep command module. |

## Verification

Completion requires:

1. Deterministic tests through the fake interpreter adapter.
2. Correct intent and position for all curated canonical cases.
3. No execution for ambiguous, irrelevant, or insufficiently confident state changes.
4. Coverage of pending creation, completion, confirmation, rejection, cancellation, replacement, and clearing.
5. Coverage of the bounded start-plus-move composition.
6. Credential-gated live Jev evaluation and threshold calibration.
7. Browser and standalone smoke tests through the common backend command route.
8. Updated architecture sources and rendered documentation.
9. A current-worktree audit covering tracked and ignored files, with the ADR as the only historical-reference allowlist.

Ignored runtime cleanup includes stale inference logs, downloaded model files, and PID files. Deletion happens only during the authorized implementation phase.
