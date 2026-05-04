# Voice Tic-Tac-Toe

> A conversational, voice-controlled tic-tac-toe game powered by speech recognition, small language models (SLM), and text-to-speech synthesis.

Play tic-tac-toe entirely through voice commands — or use your browser's built-in speech recognition. Two modes, one game.

## What Is This?

This is an **educational project** that demonstrates how a finetuned Small Language Model (SLM) can serve as the "brain" of a game — understanding natural language, parsing player intent, and calling backend functions without any hardcoded command list.

The full voice pipeline works like this:

```
Microphone → ASR (Qwen3-ASR) → Text Transcription → SLM (Gemma-4) → Intent Parsing → Game API → TTS (Kokoro-82M ONNX) → Speakers
```

Your voice is captured by the microphone, transcribed into text by the **Qwen3-ASR** automatic speech recognition model, then passed to the finetuned Gemma-4 SLM which parses your intent and calls the appropriate game backend function. Bot responses can be spoken back via Kokoro-82M ONNX TTS.

> Browser mode is also available — use Chrome/Edge's built-in Web Speech API for voice input without any GPU or local ASR model needed.

## Features

- **🎙️ Full Voice Pipeline** — Microphone → ASR transcription → SLM intent parsing → TTS playback for hands-free play
- **🌐 Browser Voice Mode** — Use Web Speech API in Chrome/Edge, no GPU needed
- **💬 Natural Language** — Speak commands like "play center" or "show me the board"
- **🧠 Finetuned Intent Engine** — Gemma-4-E4B fine-tuned on ~1,000 custom samples for natural language understanding and function calling. No fixed commands.
- **🎮 Full Game API** — REST API with win/draw detection and move validation
- **🔊 TTS Playback** — Bot responses spoken aloud via Kokoro-82M ONNX TTS; toggle on/off in browser UI
- **📱 Position Buttons** — Click-to-move grid for non-voice players

### Finetuned Model Details

The SLM is **Gemma-4-E4B**, fine-tuned specifically for this game using a custom dataset of **~1,000 samples** (817 training + 204 evaluation). The training data covers all 8 backend function calls (`start_game`, `get_board`, `place_move`, `get_status`, `greeting`, `goodbye`, `thank_you`, `intent_unclear`) with realistic voice-style input including filler words, self-corrections, and ASR artifacts for robustness. Both the model and training dataset are open-sourced on HuggingFace:

- **Model**: [moe249/google_gemma-4-E4B-it-tictactoe](https://huggingface.co/moe249/google_gemma-4-E4B-it-tictactoe)
- **Dataset**: [moe249/tic-tac-toe](https://huggingface.co/datasets/moe249/tic-tac-toe)
- **Training data**: ~1,000 samples (817 train + 204 eval) — fully open-source under MIT license

## Architecture

### Two Parallel Modes

**1. Full Voice Pipeline**
```
Microphone → ASR (Qwen3-ASR) → SLM (Gemma-4) → Orchestrator → Game API → TTS (Kokoro-82M ONNX) → Speakers
```

**2. Browser Voice Mode**
```
Microphone / Typing → /api/voice/command → SLM (Gemma-4) → Orchestrator → Game API
                                                ↓
                              Frontend: GET /api/game (re-render) + POST /api/voice/synthesize (optional TTS)
```
Both modes share the same game backend and can coexist in the same session. The browser mode TTS is toggleable via a checkbox in the UI.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | 3.10+ |
| **uv** | [Install via](https://docs.astral.sh/uv/getting-started/installation/) `curl -LsSf https://astral.sh/uv/install.sh | sh` |
| **llama.cpp** | For SLM server — build from [source](https://github.com/ggerganov/llama.cpp) or download prebuilt binaries. Required: `llama-server` on PATH |
| **hf CLI** | For model downloads — `uv pip install hf` |
| **GPU** | Optional — CUDA (NVIDIA) or Vulkan (AMD/Intel) supported for ASR/TTS acceleration and SLM inference. Browser mode does not require a GPU. |
| **Browser** | Chrome or Edge (for Web Speech API support) |

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/moedesux/voice-tic-tac-toe.git
cd voice-tic-tac-toe
```

### 2. Download Models

Run the automated download script (requires `hf` CLI):

```bash
chmod +x download_models.sh
./download_models.sh
```

This downloads four models to `./models/`:
- **Qwen3-ASR-0.6B** — Automatic Speech Recognition (1.5 GB)
- **Kokoro-82M** — Text-to-Speech (311 MB ONNX + 25 MB voices)
- **gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf** — SLM for game logic (~400 MB)

Total download: ~2.2 GB.

### 3. Install Python Dependencies

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Quick Start

#### Start All Servers + Game

```bash
chmod +x voice_game.sh
./voice_game.sh
```

This starts:
- **Backend API** on `http://localhost:8002`
- **SLM Server** (Gemma-4) on port `8080`
- **Voice Game** (full audio pipeline)

After startup, open **http://localhost:8002** in Chrome or Edge.

#### Alternative: Browser Mode Only

For a lighter setup (no ASR/TTS, no GPU needed):

```bash
# Start backend API only
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8002

# Start SLM server
llama-server -m ./models/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf --port 8080 --threads 4
```

Then open **http://localhost:8002** and use the microphone button or type commands directly.

#### Simulation Mode (No Microphone)

```bash
./voice_game.sh --simulation
```

Type commands directly in the terminal.

## Configuration

All configuration is split across two files:

### Infrastructure Config (`config/voice.conf`)

INI file for model paths, ports, and service settings:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `[slm]` | `port` | `8080` | SLM server port |
| `[slm]` | `model_path` | `./models/gemma-4-e4b-it-tictactoe-finetune.Q4_K_M.gguf` | SLM model file |
| `[asr]` | `model_path` | `./models/Qwen3-ASR-0.6B` | ASR model directory |
| `[tts]` | `enabled` | `true` | Enable/disable TTS (saves memory when false) |
| `[tts]` | `voice` | `af_sarah` | TTS voice identity |
| `[tts]` | `speed` | `1.0` | Speech speed multiplier |
| `[tts]` | `lang` | `en-us` | Language tag |
| `[backend]` | `port` | `8002` | Backend API port |

### Game Settings (`voice_game_config.py`)

Python module for game logic configuration:

| Constant | Description |
|----------|-------------|
| `SYSTEM_PROMPT` | Full system prompt with position mapping for the SLM |
| `GAME_TOOLS` | List of valid tool names (e.g., `start_game`, `place_move`, `get_board`) |
| `SUCCESS_TEMPLATES` | Response messages for each tool result |
| `EXIT_COMMANDS` | Phrases that end the game session |
| `ROW_NAMES` / `COL_NAMES` | Board position names |

### TTS Toggle

TTS playback can be disabled in two ways:

1. **Per-session** — Use the "🔊 Bot speaks responses" checkbox in the browser UI (default: enabled)
2. **Global** — Set `enabled = false` in `[tts]` section of `config/voice.conf`; the TTS model is never loaded, saving memory and startup time

## How to Interact

The SLM understands **natural language** — no memorized commands needed. Speak or type freely, and it interprets your intent:

| Intent         | Natural Language Examples                                                                      |
| -------------- | ---------------------------------------------------------------------------------------------- |
| **Start a game**   | "Let's play tic-tac-toe!" / "I want to play" / "New game" / "Wanna go?"                        |
| **Show the board** | "Where are we?" / "Show me the board" / "What does the board look like?" / "Current position?" |
| **Make a move**    | "I'll take the center" / "Top left for me" / "Put mine in position 5" / "Row 1, column 2"      |
| **Check status**   | "Who's winning?" / "What's the current state?" / "My turn or theirs?" / "Did I win?"           |
| **Chat**           | "Hello!" / "Good morning!" / "You're good at this" / "Nice move!"                              |
| **End the game**   | "I'm out" / "Good game, bye" / "Let's finish up" / "See you later"                             |

### Position Understanding

The model understands multiple ways to specify a board position — no lookup table required:

- **Natural names**: "top-left", "center", "bottom-right", "middle left"
- **Numbers 1–9**: "position 5" (center), "cell 7" (bottom-left)
- **Row/column**: "row 1, col 3" or "row 2, col 1"

The model also handles common variations and colloquialisms: "top middle", "centre" (British spelling), "spot one", etc.

## Project Structure

```
voice-tic-tac-toe/
├── voice_tic_tac_toe.py          # Full voice game entry point
├── voice_game_orchestrator.py    # Dialogue manager + SLM client
├── voice_game_interface.py       # Backend API HTTP client
├── asr.py                        # Qwen3-ASR module
├── tts.py                        # Kokoro-82M ONNX TTS module
├── config.py                     # Configuration loader
├── voice_game_config.py          # Game settings (system prompt, tools, positions)
├── download_models.sh            # Automated model downloader
├── voice_game.sh           # Server launcher and manager
├── requirements.txt              # Python dependencies
├── backend/
│   ├── main.py                   # FastAPI server (port 8002)
│   ├── game.py                   # Pure game logic
│   └── models.py                 # Pydantic API models
├── config/
│   └── voice.conf                # Infrastructure config (model paths, ports)
├── frontend/
│   ├── index.html                # Voice game page
│   ├── regular_game.html         # Regular game page
│   └── static/                   # JS + CSS assets
├── models/                       # Downloaded ML models
├── logs/                         # Runtime logs
└── test/                         # Test scripts
```

## Server Management

The launcher script manages all servers:

```bash
./voice_game.sh           # Start all servers + launch game
./voice_game.sh start     # Start servers only
./voice_game.sh stop      # Stop all servers
./voice_game.sh restart   # Restart everything
./voice_game.sh status    # Show server status
./voice_game.sh --simulation   # Start + text-only game
./voice_game.sh --debug      # Start + debug logging
```

### Log Files

| Log | Path | Use Case |
|-----|------|----------|
| SLM | `logs/llama.log` | Debug SLM responses, tool parsing |
| Backend | `logs/backend.log` | Debug API calls, game state |
| Voice | `logs/voice_game.log` | Debug ASR/TTS, orchestrator flow |

Watch in real-time: `tail -f logs/*.log`

## Troubleshooting

### Model Downloads

**`hf` command not found**
```bash
uv pip install hf
```

**Model download fails**
- Ensure you have a HuggingFace account with access to the models
- ASR model: `Qwen/Qwen3-ASR-0.6B`
- Kokoro TTS models: downloaded automatically by `download_models.sh` from GitHub releases
- SLM model: `moe249/google_gemma-4-E4B-it-tictactoe`

### Server Issues

**llama-server not found**
```bash
# Build from source
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
cmake -B build
cmake --build build --config Release --target llama-server
sudo cp build/bin/llama-server /usr/local/bin/
```

**Port already in use**
```bash
# Find and kill the process
lsof -i :8002   # Backend
lsof -i :8080   # SLM
kill -9 <PID>
```

**Backend won't start**
```bash
# Verify dependencies
uv pip install fastapi uvicorn
# Check logs
cat logs/backend.log
```

### Voice / Browser Issues

**Web Speech API not working**
- Use Chrome or Edge (Firefox/Safari don't support it)
- Grant microphone permissions when prompted
- Some browsers require HTTPS — for local dev, use `http://localhost`

**ASR/TTS fails (full voice mode)**
- Kokoro TTS runs on CPU by default; GPU (CUDA/Vulkan) optional for faster synthesis
- ASR requires GPU (CUDA) for reasonable speed
- Ensure `qwen_asr` and `kokoro_onnx` are installed:
   ```bash
   uv pip install -r requirements.txt
   ```

**"I didn't understand that"**
- Check browser console (F12) for errors
- Verify SLM server is healthy: `curl http://localhost:8080/v1/models`
- Try simpler commands like "start game" or "show board"

### GPU Diagnostics

Check GPU availability:
```bash
curl http://localhost:8002/api/health/gpu
```

Check startup logs for device info:
```bash
tail -f logs/voice_game.log | grep -E '\[ASR\]|\[TTS\]'
```

Expected output:
- `[ASR] Using CUDA GPU: <device_name>` — GPU acceleration active
- `[TTS] Using CUDA/Vulkan/CPU via ONNX Runtime` — Kokoro TTS device info
- `[ASR] Running on CPU (no compatible GPU found)` — GPU not available

### Browser Status Badges

The voice game page shows real-time status badges in the top bar:
- **Backend**: FastAPI server health
- **SLM**: Small language model availability (proxied through backend)
- **ASR**: Speech recognition model status (shows device type: CPU/CUDA/Vulkan)
- **TTS**: Speech synthesis model status (shows device type: CPU/CUDA/Vulkan)

Hover over a badge to see detailed status and last-check timestamp.

## Testing

```bash
# Tool call tests (no servers needed)
uv run python test/simple_tool_calls.py

# Full integration test (real SLM, mock ASR/TTS)
uv run python test/voice_game.py
```

## License

MIT License — see [LICENSE](LICENSE) file.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

*Built with Python, FastAPI, llama.cpp, Qwen3 ASR, Kokoro-82M ONNX TTS, and Gemma-4 SLM. Updated May 4, 2026.*
