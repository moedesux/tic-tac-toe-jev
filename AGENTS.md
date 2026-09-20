# Voice-Controlled Tic-Tac-Toe: Agent Guidance

High-signal operational documentation for OpenCode agents working on this voice-controlled tic-tac-toe project.

## Architecture

See the full architecture diagram: [architecture.drawio](./architecture.drawio)

### Quick Overview

Two parallel modes:

**1. Full Voice Pipeline:**
```
Microphone → ASR (Qwen3-ASR) → SLM (Gemma-4) → Orchestrator → Game API → TTS (Kokoro-82M ONNX) → Audio Output
```

**2. Browser Voice Mode (Frontend → SLM):**
```
User Input (voice/typing) → /api/voice/command → SLM (Gemma-4) → Orchestrator → Game API → /api/voice/synthesize → Audio Output
```

For the complete architecture diagram with all components, connections, and configuration layers, open `architecture.drawio` in [draw.io](https://app.diagrams.net/).

## Core Components

| Component           | Location                      | Port/Role                                                                                           |
| ------------------- | ----------------------------- | --------------------------------------------------------------------------------------------------- |
| **Backend API**       | `backend/main.py`               | FastAPI on 8002 — serves frontend and delegates `/api/game` and `/api/game/move` to the shared session; also serves `/api/voice/command`, `/api/voice/synthesize`, `/api/config/templates`, `/api/health/gpu` |
| **Game Session**      | `backend/game_session.py`       | Reusable asynchronous in-process boundary owning the active game state and its single `asyncio.Lock`; exposes create, read, and move operations |
| **Game Logic**        | `backend/game.py`               | Pure game logic: `check_winner()`, `get_winning_line()` (returns winning cell combo), `validate_move()`, `apply_move()` |
| **API Models**        | `backend/models.py`             | Pydantic models with `GameResponse.status` pattern validation (`^(ongoing|completed|draw)$`)            |
| **SLM Server**        | llama.cpp server              | Port 8080 (moe249/google_gemma-4-E4B-it-tictactoe model)                                                                      |
| **Voice Pipeline**    | `voice_tic_tac_toe.py`          | Full voice game with ASR → Orchestrator → TTS                                                         |
| **Frontend**          | `frontend/`                      | Two pages: `index.html` (voice game), `regular_game.html` (regular game)                               |
| **SLM Orchestrator**| `voice_game_orchestrator.py`    | SLMClient + TextOrchestrator — intent parsing, conversation history, function routing                  |
| **Voice Interface**   | `voice_game_interface.py`       | Wrapper around FastAPI backend — position conversion (2D↔1D), API calls                                |
| **Voice Synthesis**   | `backend/main.py`               | `POST /api/voice/synthesize` — Synthesizes text to base64-encoded WAV audio via Kokoro-82M ONNX TTS. Lazy-loaded singleton with double-checked locking. |
| **SLM Proxy**         | `backend/main.py`               | `GET /api/health/slm` — Proxies SLM health check through backend to avoid CORS issues in browser. |

## Critical Configuration

### voice_game_config.py — Voice Game Settings (Preferred)
All voice game configuration is now defined as clean Python constants in `voice_game_config.py`:
- `SYSTEM_PROMPT` - Full system prompt with position mapping for the SLM
- `GAME_TOOLS` - List of valid tool names
- `GAME_TOOLS_SLOT_DESCRIPTIONS` - Slot descriptions for each tool
- `SLOT_REQUIREMENTS` - Which arguments each tool needs
- `SLOT_PROMPTS` - Guidance for SLM when asking for missing arguments
- `SUCCESS_TEMPLATES` - Response messages for each tool result
- `EXIT_COMMANDS` - Phrases that end the game session
- `CLARIFICATION_CAPABILITIES` - What the SLM can help with
- `ROW_NAMES`, `COL_NAMES` - Board position names
- `POSITION_MAPPINGS` - Name → coordinates mapping

**To update the system prompt or any game setting, edit `voice_game_config.py` directly.**

### voice.conf (INI — Infrastructure Only)
`voice.conf` now contains ONLY infrastructure settings:
- **Model paths**: `./models/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf`
- **SLM settings**: URL, port, max tokens
- **ASR/TTS settings**: Model paths, sample rate

**⚠️ Tool names are case-sensitive and must match training data exactly.**

### tts_enabled — TTS Toggle
`voice.conf` now supports a TTS enable/disable flag under the `[tts]` section:
- `tts_enabled = true` (default) — TTS model loads and synthesizes responses
- `tts_enabled = false` — TTS model is never loaded; responses are text-only

When disabled, both the standalone voice game (`voice_tic_tac_toe.py`) and the backend skip TTS model loading entirely.

### System Prompt
The system prompt in `voice_game_config.py` includes explicit position mappings:
- "top-left", "top right", "bottom-left", "bottom right" → corners
- "top-center", "middle-left", "middle-right", "bottom-center" → edges
- "center" → exact center (row=1, col=1)
- "middle right" → row=1 (middle) + col=2 (right) = {row:1, col:2}
- "middle" alone → center (row=1, col=1)

## Commands Reference

```bash
# Start all servers + launch voice game
./voice_game.sh

# Start only (no game)
./voice_game.sh start

# Stop all servers
./voice_game.sh stop

# Check status
./voice_game.sh status

# Run test script (real SLM, mock ASR/TTS)
uv run python test/test_voice_game.py

# Run simulation mode (text input instead of voice)
./voice_game.sh --simulation

# Run tool call tests (no servers needed)
uv run python test/test_simple_tool_calls.py

# Comprehensive tool call tests
uv run python test/test_all_tool_calls.py

# Check GPU availability for ASR/TTS
curl http://localhost:8002/api/health/gpu
```

## Log Locations & Usage

| Log File | Contents | When to Check |
|----------|----------|---------------|
| `./logs/llama.log` | SLM verbose logs (request/response details, timings) | Debug SLM calls, tool parsing |
| `./logs/backend.log` | FastAPI access logs and errors | Debug API calls, game state |
| `./logs/voice_game.log` | TTS loading status, GPU diagnostics (`[ASR]`, `[TTS]` messages), synthesis errors | Debug TTS loading, GPU status |

**Pro tip**: Use `tail -f` to watch logs in real-time:
```bash
tail -f ./logs/llama.log        # Verbose SLM requests/responses
tail -f ./logs/backend.log       # API calls
tail -f ./logs/voice_game.log    # Voice game output
```

## Critical Gotchas (Verified)

### 1. "Cancel Task" Messages Are Normal
**Observation**: Messages containing "cancel task" appear in `llama.log` AFTER 200 responses during slot cleanup.
**Action**: **IGNORE** - These are not errors, just llama.cpp slot management.

### 2. Verbose Logging Is Enabled
**Fact**: `--verbose` flag on llama-server captures full request/response cycles.
**Value**: Check `llama.log` to see exact SLM inputs/outputs and timing.

### 3. Voice Game Requires Specific Modules
**Failure**: Installation fails without `qwen_asr` and `kokoro_onnx`.
**Solution**: Install all deps at once:
      ```bash
      uv pip install -r requirements.txt
      ```

### 4. Model Name Must Match Exactly
**Wrong**: `gemma-4-Q3_K_M.gguf` or `model`
**Correct**: `gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf`
**Location**: `./models/` directory

### 5. HTTP/1.1 Required for llama.cpp
**Issue**: llama.cpp doesn't fully support HTTP/2.
**Solution**: SLMClient already uses `httpx.Client(http2=False)` - verify this is maintained.

### 6. Frontend Conditional Polling
**Fact**: `frontend/static/app.js` polls `/api/game` every 2 seconds and **stops automatically** when `gameOver` becomes `true`.
**Use case**: Shows voice game moves on frontend without manual refresh; avoids unnecessary requests after game ends.

### 7. Frontend Cache-Busting
**Issue**: Static JS files may be cached by the browser, showing stale code.
**Solution**: Use the built-in cache-buster IIFE in HTML files that dynamically appends `?v=<timestamp>` to all script/src and stylesheet/href attributes. Also hard-refresh browser (Ctrl+Shift+R).

### 8. `/api/voice/command` Endpoint
**Purpose**: Bridges frontend voice UI to SLM pipeline.
**Request**: `POST /api/voice/command` with JSON body `{"command": "user text"}`
**Response**: JSON `{success, response, function, arguments}`
**Orchestrator**: Module-level singleton — conversation history persists across requests for multi-turn context.

### 9. `GameEndRequested` Exception
**Fact**: `asr.py` raises `GameEndRequested` (custom exception) instead of calling `exit()` to gracefully end the voice game.
**Action**: `voice_tic_tac_toe.py` catches `GameEndRequested` alongside `KeyboardInterrupt` and `EOFError` for clean shutdown.

### 10. TTS Timeout
**Fact**: Voice commands have a 60-second timeout (`VOICE_COMMAND_TIMEOUT`). If the SLM doesn't respond within 60s, the request is aborted and the mutex is released.
**Action**: The frontend shows a "Thinking..." indicator during processing. If timeout occurs, an error toast is displayed.

## Dependencies

### Python (via uv)
```txt
# API Framework
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.3
httpx>=0.28.0

# Testing
pytest>=7.4.3

# Deep Learning
torch>=2.0.0
transformers==4.57.6    # pinned for qwen compatibility
accelerate>=1.12.0
numpy>=1.24.0

# Voice Processing
qwen_asr>=0.0.6
kokoro_onnx>=0.5.0
onnxruntime>=1.16.0
sounddevice>=0.4.0
soundfile>=0.13.0

# Audio Utilities
sox>=1.5.0
soxr>=1.0.0
audioop-lts>=0.2.2
typing-extensions>=4.10.0

# External APIs
openai>=1.0.0
```

### Dependency Management
- **Use `uv` for ALL dependency management** — never use `venv` or `pip` directly in scripts
- Virtual environments: `uv venv .venv`
- Install dependencies: `uv pip install -r requirements.txt` or `uv pip install <package>`
- Run scripts with deps: `uv run --with-requirements requirements.txt python script.py`
- Shell scripts must use `uv run` or `uv pip install`, never `source .venv/bin/activate` or `pip install`

### System
- `llama-server` (from llama.cpp) - For SLM
- `uvicorn` - For FastAPI backend
- `sox`, `libsox-dev` - For audio processing (optional, for real voice input)

## Testing

### Tool Call Tests (No servers needed)
**Note**: These tests require the SLM server to be running on port 8080. Without it, all tests will show `APIConnectionError`.
```bash
# Quick test (30 cases, 100% pass rate)
uv run python test_simple_tool_calls.py

# Comprehensive test (48 cases, with statistics)
uv run python test_all_tool_calls.py
```

### Integration Test (Real SLM)
```bash
uv run python test_voice_game.py
```
- Uses real SLM server
- Mocks ASR/TTS for reproducibility
- Validates end-to-end flow

### Game State Verification
Win and draw scenarios are tested via API smoke tests:
- Win: `winner: "X"`, `status: "completed"`, `gameOver: true`
- Draw: `winner: null`, `status: "draw"`, `gameOver: true`
- Post-game moves rejected with `"Game already completed"`

### Simulation Mode (Text Input)
```bash
./voice_game.sh --simulation
```
- No voice input required
- Type commands directly
- Useful for rapid iteration

### Full Voice Pipeline (Real microphone)
```bash
# From the project root directory:
source .venv/bin/activate && python voice_tic_tac_toe.py
```
- Requires physical microphone or virtual audio device
- Full ASR → SLM → Orchestrator → Game API → TTS pipeline

### Browser Voice Mode (Web Speech API)
Open `http://localhost:8002/` in Chrome/Edge:
- Click microphone button → speaks → auto-submits via `/api/voice/command`
- Or type commands in text input and press Send
- Or use Quick Command buttons or Position Buttons

## File Ownership & Structure

| File                       | Owner             | Purpose                                                                                               |
| -------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------- |
| `backend/main.py`            | FastAPI game API  | `/api/game`, `/api/game/move`, `/api/voice/command`, `/api/voice/synthesize`, `/api/config/templates`, `/api/health/gpu` endpoints. Owns the game-session singleton/accessor and lazy TTS/ASR singletons; game routes delegate to the session. |
| `backend/game_session.py`    | Game session      | Reusable asynchronous in-process boundary that owns the active game state and single `asyncio.Lock`; serializes create, read, move, and ensure-created operations. |
| `backend/game.py`            | Game logic        | Pure game logic: `check_winner()`, `get_winning_line()` (returns winning cell combo), `validate_move()`, `apply_move()` |
| `backend/models.py`          | API models        | Pydantic models with `GameResponse.status` pattern validation (`^(ongoing|completed|draw)$`)            |
| `voice_game_orchestrator.py` | Orchestrator      | SLMClient (JSON parsing, tool calling) + TextOrchestrator (conversation management, function routing). Thread-safe lazy init with `threading.Lock()`. Cached tool definitions. |
| `voice_game_interface.py`    | HTTP client       | Communicates with backend API, position conversion. `timeout=10` on all requests with error handling. Robust path resolution via `os.path.dirname`. |
| `voice_tic_tac_toe.py`       | Main entry        | Full voice game with push-to-talk I/O loop                                                            |
| `asr.py` / `tts.py`            | Voice modules     | Qwen3-ASR transcription + Kokoro-82M ONNX synthesis. Stores `device_type` attribute for health reporting. `asr.py` raises `GameEndRequested` (custom exception) instead of `exit()` for graceful shutdown. |
| `config/voice.conf`    | Config            | INI with JSON values for ASR/TTS/SLM                                                                  |
| `config.py`                  | Config loader     | Thin wrapper for infrastructure-only settings. All voice game settings migrated to voice_game_config.py |
| `voice_game_config.py`       | Config constants  | SYSTEM_PROMPT, GAME_TOOLS, SUCCESS_TEMPLATES, POSITION_MAPPINGS (derived programmatically from ROW_NAMES/COL_NAMES) |
| `frontend/index.html`        | Frontend          | Voice game page (Web Speech API, quick commands, position buttons, TTS playback)                                                      |
| `frontend/regular_game.html` | Frontend          | Regular game page                                                                                     |
| `frontend/static/app.js`     | Frontend          | Game logic: conditional polling (stops when `gameOver`), win/draw detection (`getWinningLine`), toast notifications, fetches templates from `/api/config/templates` with fallback defaults |
| `frontend/static/style.css`  | Frontend          | Retro 70s-80s styling + mic pulse animation + win/draw animations (`winPulse`, `statusPop`) + toast notification styles |
| `test_simple_tool_calls.py`  | Tests             | 30 test cases for all 8 tool calls                                                                    |
| `test_all_tool_calls.py`     | Tests             | 48 comprehensive test cases with statistics                                                           |
| `test_voice_game.py`         | Tests             | Full integration test (real SLM, mock ASR/TTS)                                                        |
| `backend/api_endpoints.py`     | API constants   | Defines endpoint constants (GAMES_ENDPOINT, GAME_BY_ID_ENDPOINT, GAME_MOVES_ENDPOINT) imported by voice_game_interface.py                         |
| `backend/__init__.py`          | Package init    | Makes backend/ a Python package                                                                                                                  |
| `config/__init__.py`           | Package init    | Makes config/ a Python package                                                                                                                   |
| `config/backend.conf`          | Backend config  | Backend configuration (PORT, HOST, API_TITLE, API_VERSION)                                                                                       |
| `scripts/generate_training_data.py` | Training data | Generates 800 training + 200 eval samples for SLM finetuning                                                            |
| `test/test_transcribe.py`      | Tests           | Transcription test                                                                                                                               |
| `REVIEW.md`                    | Review          | Code review findings document                                                                                                                    |
| `assets/default_voice.wav`     | Assets          | Default voice WAV file                                                                                                                           |

## Common Issues & Solutions

| Issue | Symptom | Solution |
|-------|---------|----------|
| Module not found | `ModuleNotFoundError: No module named 'qwen_asr'` | `uv pip install qwen_asr kokoro_onnx` |
| HTTP/2 error | `HTTP/2 protocol negotiation failed` | Verify SLMClient uses `http2=False` |
| No SLM requests | Empty `llama.log` | Verify servers started: `./voice_game.sh status` |
| Frontend stale/stuck | Old code showing, commands fail | Hard-refresh browser (Ctrl+Shift+R); JS cache-busting via IIFE |
| "I didn't understand that" | Command not reaching SLM | Check browser console for errors; verify `/api/voice/command` endpoint returns 200 |
| Model fails | "Model loading failed" | Verify `./models/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf` exists |
| Log spam | "cancel task" in `llama.log` | **IGNORE** - normal slot cleanup |
| Web Speech API not working | Mic button does nothing | Use Chrome/Edge; some browsers block mic without HTTPS |
| Config not found | `ImportError` or missing keys | Verify `voice_game_config.py` imports in config.py; voice game settings are now in Python constants |
| Port 8002 conflict | `uvicorn fails to start: [Errno 98] Address already in use` | `lsof -i :8002 | grep LISTEN | kill -9 <PID>` or use different port |

## Architecture Notes

### Shared State
- `backend/game_session.py` owns the authoritative active game state and single asynchronous session boundary
- `backend/main.py` owns the session singleton and accessor; REST handlers and voice setup use that boundary
- Both frontend (regular + voice) and voice game use same session
- State persists across frontend refreshes and voice sessions

### Thread Safety
- `GameSession`'s single `asyncio.Lock()` serializes all shared game-state reads and mutations, including REST operations and voice setup
- `threading.Lock()` (`_orchestrator_lock`) protects lazy initialization of the SLM orchestrator singleton via double-checked locking in `_get_orchestrator()`
- All `requests` calls in `voice_game_interface.py` use `timeout=10` with `Timeout`/`RequestException` handling to prevent indefinite hangs

### SLM Tool Calling Format
**Response structure:**
```json
{
  "choices": [{
    "message": {
      "reasoning_content": "Thought process here",
      "tool_calls": [{
        "function": {
          "name": "place_move",
          "arguments": "{\"row\": 1, \"col\": 2}"
        }
      }]
    }
  }]
}
```

**Parsing:**
```python
tool_name = response.choices[0].message.tool_calls[0].function.name
arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
```

### Conversation History
- Accumulated across turns for context
- Passed to SLM with each request
- Enables multi-turn dialog (e.g., "I want to play" → "Where do you want to go?")
- Persisted in `TextOrchestrator.conversation_history` (module-level singleton)

### SLMClient JSON Parsing
Robust extraction with 5 patterns:
1. Proper `tool_calls` in response (highest priority)
2. JSON in `content` field (markdown blocks, triple quotes, balanced braces)
3. JSON in `reasoning_content` field
4. Priority-based fallback regex patterns (4 levels)
5. Final fallback: `intent_unclear`

### Frontend Voice Command Flow
```
User Input (mic/text/buttons) → executeVoiceCommand() → POST /api/voice/command → SLM → Orchestrator → /api/game → re-render
```

## Environment

| Property | Value |
|----------|-------|
| **Platform** | Linux |
| **GPU** | Vulkan (AMD Radeon) |
| **Backend** | llama.cpp uses Vulkan backend |
| **CPU** | Multi-core (4 threads used by default) |

## Recent Changes (April 30, 2026 — Status Fix)

### Bug Fixes (P0)
- **SLM status badge fix** — Changed frontend to proxy SLM health through `/api/health/slm` backend endpoint (avoids CORS blocking from browser)
- **ASR/TTS status display** — Health endpoints now trigger model loading and report CUDA/Vulkan/CPU device type; frontend shows status badges with device info; `./voice_game.sh status` includes ASR/TTS
- **New health endpoints** — `GET /api/health/slm`, `GET /api/health/tts`; enhanced `/api/health/asr` to return device info

## Recent Changes (May 2, 2026)

### TTS Migration (P0)
- **Kokoro-82M ONNX replaces Qwen3-TTS** — 82M parameter ONNX model, ~96x real-time on GPU, runs on CPU. Apache 2.0 license
- **Async TTS fix** — `tts.synthesize()` wrapped in `asyncio.to_thread()` to prevent event loop blocking (5-30s freeze)
- **TTS toggle fix** — Frontend "🔊 Bot speaks responses" checkbox now properly respected; `ttsEnabled` module variable synced with localStorage
- **download_models.sh updated** — Removed Qwen TTS download, added Kokoro model downloads (kokoro-v1.0.onnx + voices-v1.0.bin)
- **config/voice.conf** — New Kokoro settings: `voices_path`, `voice` (af_sarah), `speed`, `lang`, `sample_rate` (24000)
- **voice_game.sh** — Pre-flight check updated for `kokoro_onnx`

### Commits
- `a813828` — fix: respect TTS toggle checkbox in frontend
- `8996b6b` — chore: remove Qwen TTS download from download_models.sh
- `36607e2` — feat: add Kokoro TTS model downloads to download_models.sh
- `1e3c643` — feat: replace Qwen3-TTS with Kokoro-82M ONNX TTS
- `be11252` — fix: offload TTS synthesis to thread pool to prevent async event loop blocking

## Recent Changes (May 3-4, 2026)

### Fixes (P0–P3)
- **Unbound variable in voice_game.sh** — Resolved variable scope issue that caused script failures
- **Polling not starting on regular_game.html** — Fixed conditional polling initialization so moves render on the regular game page
- **Code review findings** — Addressed all P0/P1/P2/P3 findings across 15 files
- **Hardcoded backend/SLM ports** — Backend and SLM ports now read from config files instead of being hardcoded

### Refactoring
- **SLM model file rename** — Renamed model file and eliminated all hardcoded model paths across the codebase

### Cleanup
- **Dead code removal** — Removed ~240 lines of dead code across 7 files
- **requirements-tts.txt merged** — Merged into `requirements.txt`; removed standalone file
- **Stale Qwen3-TTS references** — Removed remaining references to deprecated Qwen3-TTS

### Documentation
- **AGENTS.md + README.md** — Updated for Kokoro TTS migration

### Commits
- `db9cb64` — fix: resolve unbound variable in voice_game.sh and polling not starting on regular_game.html
- `da1b061` — docs: emphasize educational intent, ASR pipeline, natural language interaction
- `335e9f8` — refactor: rename SLM model file and eliminate hardcoded model paths
- `086e0b7` — fix: address all code review findings (P0/P1/P2/P3) across 15 files
- `d35d43e` — chore: remove ~240 lines of dead code across 7 files
- `51f71e6` — fix: read backend/SLM ports from config instead of hardcoding
- `eed0968` — chore: merge requirements-tts.txt into requirements.txt
- `002c0ce` — chore: remove remaining stale Qwen3-TTS references
- `8bf691d` — docs: update AGENTS.md and README.md for Kokoro TTS migration
- `54ce48b` — fix: add missing numpy import in TTS synthesis endpoint (added test_transcribe.py, assets/default_voice.wav)

## Recent Changes (April 30, 2026)

### New Features (P0)
- **Waiting indicator** — "Thinking..." dot-flashing animation during SLM command processing; 60-second timeout with mutex guard
- **TTS playback (browser mode)** — `POST /api/voice/synthesize` endpoint returns base64 WAV audio; frontend plays via AudioContext
- **TTS toggle** — `tts_enabled` config option in `voice.conf`; frontend checkbox to enable/disable speech; model never loads when disabled
- **GPU diagnostics** — `[ASR]` / `[TTS]` startup messages report CUDA/Vulkan/CPU status; `GET /api/health/gpu` endpoint
- **Conditional TTS loading** — `voice_tic_tac_toe.py` skips TTS model when `tts_enabled = false`

## Recent Changes (April 22, 2026)

### Config Simplification (P1)
- **System prompt removed from voice.conf** — SYSTEM_PROMPT moved permanently to `voice_game_config.py`; `VoiceConfig` now only contains infrastructure settings (model paths, ports, sample rates)
- **`get_system_prompt()` removed** — `SYSTEM_PROMPT` imported directly as module-level constant in `voice_game_orchestrator.py`
- **Game constants imported directly** — `GAME_TOOLS`, `SUCCESS_TEMPLATES`, `ROW_NAMES`, `COL_NAMES`, `POSITION_MAPPINGS` imported from `voice_game_config.py` instead of via `get_voice_config()`
- **`get_voice_config()` deprecated** — Still available for infrastructure-only settings (model paths, ports), but NOT for game settings
- **`config/tests/` deleted** — All unit tests for config module removed (no longer needed — config is now thin wrapper + Python constants)
- **`MIGRATION.md` deleted** — Outdated migration guide referencing ConfigLoader and removed features

## Recent Changes (April 21, 2026)

### Critical Fixes (P0)
- **`asyncio.Lock()`** — Added `game_lock` to protect all `current_game` reads/writes in `backend/main.py` (CRIT-1)
- **Request timeouts** — Added `timeout=10` with `Timeout`/`RequestException` handling to all `requests` calls in `voice_game_interface.py` (CRIT-2)
- **Graceful shutdown** — Replaced `exit()` with `GameEndRequested` custom exception in `asr.py`; `voice_tic_tac_toe.py` catches it for clean shutdown (CRIT-3)

### Major Fixes (P1)
- **Thread-safe orchestrator init** — Added `threading.Lock()` with double-checked locking in `_get_orchestrator()` to prevent TOCTOU race (MAJ-1)
- **`game_started` flag sync** — Replaced unconditional `orchestrator.game_started = True` with state-synced check against actual `current_game` status (MAJ-2)
- **Grammar fix** — Fixed "understood" → "understand" in frontend error message (MAJ-3)
- **Draw detection** — Fixed `status_to_description()` to check `status["status"] == "draw"` instead of `== "completed"` (MAJ-5)

### Minor Improvements (P2)
- **Tool caching** — Cached `_build_tools()` at module level via `_get_cached_tools()` (MIN-1)
- **Path resolution** — Replaced fragile `sys.path.insert` with `os.path.dirname(os.path.abspath(__file__))` (MIN-2)
- **Unused import** — Removed unused `import random` from `voice_game_orchestrator.py` (MIN-3)
- **Templates endpoint** — Added `GET /api/config/templates` endpoint; frontend fetches from API with fallback defaults (MIN-4)
- **Conditional polling** — Frontend polling stops automatically when `gameOver` is `true` (MIN-5)
- **Toast notifications** — Replaced `alert()` with CSS-animated toast notifications (MIN-6)
- **Status semantics comments** — Added clarifying comments for status field values in `make_move()` (MIN-7)

### Commits
- `cb46ad3` — CRIT + MAJ fixes (10 files, +565/-445 lines)
- `b3b10a4` — MIN fixes (6 files, +187/-41 lines)

## Recent Changes (April 17, 2026)

### New Features
- **`/api/voice/command` endpoint**: Full SLM pipeline accessible from frontend
- **Browser voice mode**: Web Speech API integration in `index.html`
- **Quick command buttons**: Start Game, Show Board, Check Status, Quit
- **Position buttons**: 3x3 grid for direct move placement
- **Conversation history**: Multi-turn context preserved across commands

### Config Migration (April 17, 2026)
- **`voice_game_config.py`** — NEW FILE: All voice game settings as Python constants
- **`config.py`** — `VoiceConfig` now imports from `voice_game_config.py`
- **`voice_game_orchestrator.py`** — Updated to use constants from module
- **`voice.conf`** — Cleaned up: only infrastructure settings remain
- **System prompt** — Full natural language position mapping added (fixes "middle right" parsing)

### Bug Fixes
- **Frontend caching**: Dynamic cache-buster IIFE prevents stale JS
- **Variable shadowing**: Renamed `arguments` parameter to `cmdArgs` in `executeVoiceCommand`
- **Voice command routing**: All frontend inputs now properly route through SLM

### Bug Fixes (April 17, 2026)
- **System prompt position mapping** — Added explicit mappings for all position phrases (fixes "middle right" → center bug)
- **Config migration** — Moved voice game config from \n-escaped INI to Python constants (voice_game_config.py)

### Testing
- **100% pass rate**: 30/30 tool call tests passing
- **All 8 tool calls verified**: greeting, start_game, get_board, place_move, get_status, thank_you, goodbye, intent_unclear

### Bug Fixes + Frontend Polish (April 17, 2026)
- **Win/draw detection** — Fixed `backend/main.py` to distinguish wins (`"X"/"O"`) from draws (`"draw"`); draws no longer blocked as "Game already completed"
- **Status validation** — Added `Field(pattern=...)` to `GameResponse.status` for `^(ongoing|completed|draw)$`
- **Win highlighting** — Frontend highlights 3 winning cells with gold flash (`winPulse` animation), status bar turns golden (`status-win`)
- **Draw indicator** — All cells gray out on draw, status bar shows muted tones (`status-draw`), text reads "It's a Draw!"
- **Status text** — Replaced generic "Game Over" with specific: "X Wins!", "O Wins!", "It's a Draw!"
- **`get_winning_line()`** — New helper in `backend/game.py` that returns the (a,b,c) tuple of winning cells

## When in Doubt

**Trust hierarchy:**
1. **Executable sources** (scripts, configs)
2. **Log files** (actual behavior)
3. **Code comments**
4. **This documentation**

**Verification workflow:**
1. Check logs first (`tail -f ./logs/*.log`)
2. Verify config with `cat config/voice.conf`
3. Inspect code if behavior deviates from docs
4. Run tests to confirm hypothesis

---

*Last verified: May 4, 2026*
*Model: moe249/google_gemma-4-E4B-it-tictactoe* (GGUF: `gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf`)
*SLM port: 8080 | Backend port: 8002*
