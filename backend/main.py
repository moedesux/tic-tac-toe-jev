"""
FastAPI application for Tic-Tac-Toe game.
Provides REST API endpoints for single game operations.
"""

import asyncio
import httpx
import json
import logging
import threading
import time
import torch
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def _serve_html_with_cache_bust(filename: str) -> HTMLResponse:
    """Read an HTML file and inject cache-busting query params into script/style tags."""
    html_path = FRONTEND_DIR / filename
    html = html_path.read_text(encoding="utf-8")
    ts = str(int(time.time() * 1000))
    html = html.replace('/static/app.js', f'/static/app.js?v={ts}')
    html = html.replace('/static/style.css', f'/static/style.css?v={ts}')
    return HTMLResponse(content=html)


from backend.models import (
    MoveCreate,
    GameResponse,
)
from config.config import get_backend_config, get_voice_config

from backend.game import check_winner, get_winning_line, validate_move, apply_move

# Module-level logger
logger = logging.getLogger(__name__)

# Module-level singleton for the voice orchestrator
# Initialized lazily on first /api/voice/command request
_orchestrator = None
_slm_client = None
_game_interface = None


def _get_orchestrator():
    """Lazily initialize and return the voice orchestrator singleton."""
    global _orchestrator, _slm_client, _game_interface

    if _orchestrator is not None:
        return _orchestrator

    with _orchestrator_lock:
        # Double-check after acquiring lock (another thread may have initialized)
        if _orchestrator is not None:
            return _orchestrator

        from voice_game_orchestrator import SLMClient, TextOrchestrator
        from voice_game_interface import VoiceGameInterface

        model_name = get_voice_config().slm_model_name
        api_key = None  # Empty for local llama.cpp server
        port = None  # Uses config value (8080)

        _slm_client = SLMClient(model_name, api_key=api_key, port=port)
        _game_interface = VoiceGameInterface()
        _orchestrator = TextOrchestrator(_slm_client, _game_interface)

        logger.info("Voice orchestrator initialized with model: %s", model_name)
        return _orchestrator


# Hardcoded static file paths (from [paths] section in backend.conf)
STATIC_MOUNT_POINT = "/static"
STATIC_DIRECTORY = Path(__file__).parent.parent / "frontend" / "static"


config = get_backend_config()
app = FastAPI(title=config.api_title, version=config.api_version)

# Single game storage
current_game: Optional[dict] = None
game_lock = asyncio.Lock()
_orchestrator_lock = threading.Lock()


def _create_initial_game(game_id: str) -> dict:
    """Create a fresh game state dictionary."""
    return {
        "gameId": game_id,
        "board": [None] * 9,
        "turn": "X",
        "winner": None,
        "status": "ongoing",
        "gameOver": False,
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": config.api_title,
        "version": config.api_version,
    }


@app.get("/api/health/asr")
async def asr_health_check():
    """Check ASR availability — triggers model loading and returns device info."""
    try:
        from qwen_asr import Qwen3ASRModel
    except (ImportError, ModuleNotFoundError) as e:
        return {
            "status": "unavailable",
            "service": "ASR",
            "device": "none",
            "error": f"Module not found: {e}"
        }

    # Trigger lazy model loading via backend singleton
    try:
        asr = _get_asr()
        device = getattr(asr, 'device_type', 'unknown')
        loaded = asr.use_real_asr if hasattr(asr, 'use_real_asr') else False
        if loaded:
            return {"status": "healthy", "service": "ASR", "device": device}
        else:
            return {"status": "degraded", "service": "ASR", "device": device, "error": "Model failed to load"}
    except Exception as e:
        return {"status": "unavailable", "service": "ASR", "device": "unknown", "error": str(e)}


@app.get("/api/health/gpu")
async def gpu_health_check():
    """Report GPU availability for ASR/TTS models."""
    try:
        return {
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count(),
            "vulkan_available": hasattr(torch.backends, 'vulkan') and torch.backends.vulkan.is_available(),
            "device": "auto",
            "note": "Models use device='auto' — PyTorch selects the best available device"
        }
    except Exception as e:
        return {
            "error": str(e),
            "cuda_available": False,
            "vulkan_available": False,
            "device": "unknown"
        }


@app.get("/api/health/slm")
async def slm_health_check():
    """Proxy SLM health check through backend to avoid CORS issues."""
    # Detect GPU availability — SLM runs on same hardware as this process
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "vulkan"):
        if torch.backends.vulkan.is_available():
            device = "vulkan"
    
    vc = get_voice_config()
    slm_url = f"http://{vc.slm_host}:{vc.slm_port}"
    async with httpx.AsyncClient(http2=False, timeout=5.0) as client:
        try:
            resp = await client.get(f"{slm_url}/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                model_name = data.get("data", [{}])[0].get("id", "unknown") if data.get("data") else "unknown"
                return {"status": "up", "service": "SLM", "model": model_name, "device": device}
            return {"status": "down", "service": "SLM", "error": f"HTTP {resp.status_code}", "device": device}
        except httpx.RequestError:
            return {"status": "down", "service": "SLM", "error": "Cannot reach SLM server", "device": device}


@app.get("/api/health/tts")
async def tts_health_check():
    """Check TTS availability — triggers model loading and returns device info."""
    try:
        from tts import KokoroTTS
    except (ImportError, ModuleNotFoundError) as e:
        return {
            "status": "unavailable",
            "service": "TTS",
            "device": "none",
            "error": f"Module not found: {e}"
        }

    try:
        tts = _get_tts()
        device = getattr(tts, 'device_type', 'unknown')
        loaded = tts.use_real_tts if hasattr(tts, 'use_real_tts') else False
        if loaded:
            return {"status": "healthy", "service": "TTS", "device": device}
        else:
            return {"status": "degraded", "service": "TTS", "device": device, "error": "Model failed to load"}
    except RuntimeError as e:
        return {"status": "disabled", "service": "TTS", "device": "none", "error": str(e)}
    except Exception as e:
        return {"status": "unavailable", "service": "TTS", "device": "unknown", "error": str(e)}


@app.get("/")
async def serve_frontend():
    """Serve the frontend index.html with cache-busted assets."""
    return _serve_html_with_cache_bust("index.html")


@app.get("/index.html")
async def serve_index():
    """Serve the frontend index.html (for /index.html URL)."""
    return _serve_html_with_cache_bust("index.html")


@app.get("/regular_game.html")
async def serve_regular_game():
    """Serve the regular game page with cache-busted assets."""
    return _serve_html_with_cache_bust("regular_game.html")


@app.post("/api/game", response_model=GameResponse)
async def create_game():
    """Create a new game (restart if game exists)."""
    global current_game

    async with game_lock:
        game_id = str(uuid.uuid4())
        current_game = _create_initial_game(game_id)

        return GameResponse(**current_game)


@app.get("/api/game", response_model=GameResponse)
async def get_game():
    """Get current game state."""
    global current_game

    async with game_lock:
        if current_game is None:
            raise HTTPException(status_code=404, detail="No game created yet")

        return GameResponse(**current_game)


@app.post("/api/game/move", response_model=GameResponse)
async def make_move(move: MoveCreate):
    """Make a move on the current game."""
    global current_game

    async with game_lock:
        if current_game is None:
            raise HTTPException(status_code=404, detail="No game created yet")

        board = current_game["board"]
        turn = current_game["turn"]

        # Validate move
        is_valid, error_message = validate_move(board, move.position, turn)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)

        # Check if game is already over
        winner = check_winner(board)
        if winner in ("X", "O"):
            raise HTTPException(status_code=400, detail="Game already completed")

        # Apply move
        new_board = apply_move(board, move.position, turn)
        next_turn = "O" if turn == "X" else "X"

        # Check for winner after move
        new_winner = check_winner(new_board)

        # Update game state
        # Status semantics:
        #   "ongoing"  — game in progress, no winner yet
        #   "completed"— game ended with a winner (X or O)
        #   "draw"     — game ended with no winner (full board, no line)
        # The `winner` field: set to "X"/"O" for wins, None for draws/ongoing.
        # The `gameOver` flag is the canonical "is game finished?" indicator.
        current_game["board"] = new_board
        current_game["turn"] = next_turn
        current_game["winner"] = new_winner if new_winner in ("X", "O") else None
        current_game["status"] = (
            "completed"
            if new_winner in ("X", "O")
            else ("draw" if new_winner == "draw" else "ongoing")
        )
        current_game["gameOver"] = new_winner is not None

        return GameResponse(**current_game)


# Serve static files
app.mount(STATIC_MOUNT_POINT, StaticFiles(directory=STATIC_DIRECTORY), name="static")


# ---------------------------------------------------------------------------
# Config Endpoints
# ---------------------------------------------------------------------------
class TemplatesResponse(BaseModel):
    """Response body for templates endpoint."""

    templates: dict[str, str]


@app.get("/api/config/templates", response_model=TemplatesResponse)
async def get_templates():
    """Return voice game response templates from config.

    This endpoint serves the same templates used by the voice orchestrator,
    preventing duplication between frontend and backend.
    """
    from config.voice_game_config import SUCCESS_TEMPLATES

    return TemplatesResponse(templates=SUCCESS_TEMPLATES)


# ---------------------------------------------------------------------------
# Voice Command Endpoint — Frontend → SLM Pipeline
# ---------------------------------------------------------------------------
class VoiceCommandRequest(BaseModel):
    """Request body for voice command endpoint."""

    command: str = Field(..., max_length=500)
    gameId: Optional[str] = None


class VoiceCommandResponse(BaseModel):
    """Response body for voice command endpoint."""

    success: bool
    response: str
    function: str
    arguments: dict


@app.post("/api/voice/command", response_model=VoiceCommandResponse)
async def voice_command(request: VoiceCommandRequest):
    """Handle voice command from frontend via SLM pipeline.

    Routes user text through the SLM (Gemma-4) for intent parsing,
    then executes the resulting game action via the orchestrator.

    Request body:
        command: User's spoken/transcribed text
        gameId:  Optional game ID (not used — backend manages state globally)

    Response:
        success: Whether the command was processed
        response: Bot's reply message
        function: The tool/function name the SLM selected
        arguments: Parsed arguments for the selected function
    """
    command = request.command.strip()

    if not command:
        return VoiceCommandResponse(
            success=False,
            response="Please say something or type a command.",
            function="",
            arguments={},
        )

    # Initialize orchestrator on first request (lazy init)
    try:
        orchestrator = _get_orchestrator()
    except Exception as e:
        logger.error("Failed to initialize orchestrator: %s", e)
        return VoiceCommandResponse(
            success=False,
            response="Voice service unavailable. Please try again.",
            function="",
            arguments={},
        )

    # Ensure a game exists and orchestrator knows about it
    global current_game

    async with game_lock:
        if current_game is None:
            # No game in backend — create one
            game_id = str(uuid.uuid4())
            current_game = _create_initial_game(game_id)

        # Sync orchestrator's game_started flag with backend state
        orchestrator.game_started = current_game is not None and current_game.get("status") != "completed" and current_game.get("status") != "draw"

        # Sync VoiceGameInterface's game_id so make_move works
        if not orchestrator.game.game_id:
            orchestrator.game.game_id = current_game["gameId"]

    # Run the synchronous orchestrator in a thread pool to avoid blocking
    def _process():
        return orchestrator.process_utterance(command)

    try:
        response_text = await asyncio.to_thread(_process)
    except Exception as e:
        logger.error("Orchestrator processing failed: %s", e, exc_info=True)
        return VoiceCommandResponse(
            success=False,
            response="An error occurred. Please try again.",
            function="",
            arguments={},
        )

    # Extract the last tool call from conversation history
    last_function = ""
    last_arguments: dict = {}

    for msg in reversed(orchestrator.conversation_history):
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            tool_call = msg["tool_calls"][0]
            last_function = tool_call["function"]["name"]

            args_raw = tool_call["function"]["arguments"]
            if isinstance(args_raw, str):
                try:
                    last_arguments = json.loads(args_raw)
                except json.JSONDecodeError:
                    last_arguments = {}
            elif isinstance(args_raw, dict):
                last_arguments = args_raw
            else:
                last_arguments = {}

            break

    # Handle None response (goodbye / exit)
    if response_text is None:
        response_text = "Thanks for playing! Goodbye!"

    return VoiceCommandResponse(
        success=True,
        response=response_text,
        function=last_function,
        arguments=last_arguments,
    )


# ============================================================================
# Voice Transcription Endpoint — Local Qwen3-ASR
# ============================================================================

# Lazy singleton ASR instance (loaded once, reused across requests)
_asr_instance = None
_asr_lock = threading.Lock()


def _get_asr():
    """Lazily initialize and return the ASR singleton."""
    global _asr_instance
    if _asr_instance is not None:
        return _asr_instance
    with _asr_lock:
        if _asr_instance is None:
            from asr import Qwen3ASR
            model_path = get_voice_config().asr_model_path
            _asr_instance = Qwen3ASR(model_path=model_path, device="auto")
    return _asr_instance


# ============================================================================
# Voice Synthesis Endpoint — Local Kokoro-82M ONNX TTS
# ============================================================================

# Lazy singleton TTS instance (loaded once, reused across requests)
_tts_instance = None
_tts_lock = threading.Lock()


def _get_tts():
    """Lazily initialize and return the TTS singleton."""
    global _tts_instance
    if _tts_instance is not None:
        return _tts_instance
    with _tts_lock:
        if _tts_instance is None:
            from tts import KokoroTTS
            vc = get_voice_config()
            if not vc.tts_enabled:
                raise RuntimeError("TTS is disabled in configuration (tts_enabled = false)")
            _tts_instance = KokoroTTS(
                model_path=vc.tts_model_path,
                voices_path=vc.tts_voices_path,
                voice=vc.tts_voice,
                speed=vc.tts_speed,
                lang=vc.tts_lang,
            )
    return _tts_instance


class TranscribeRequest(BaseModel):
    audio: str  # base64-encoded PCM float32 samples
    sample_rate: int = 16000


class TranscribeResponse(BaseModel):
    text: str


@app.post("/api/voice/transcribe", response_model=TranscribeResponse)
async def voice_transcribe(request: TranscribeRequest):
    """Transcribe audio using local Qwen3-ASR model."""
    try:
        import base64
        import numpy as np

        # Decode base64 → bytes → float32 numpy array
        audio_bytes = base64.b64decode(request.audio)
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

        # Get cached ASR instance (loaded once on first request)
        asr = _get_asr()

        # Run inference in thread pool to avoid blocking async event loop
        def _transcribe():
            return asr.transcribe(audio_array, request.sample_rate)

        text = await asyncio.to_thread(_transcribe)
        return TranscribeResponse(text=text.strip())
    except Exception as e:
        logger.error("Transcription error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


# ============================================================================
# Voice Synthesis Endpoint — Local Kokoro-82M ONNX TTS
# ============================================================================

class SynthesizeRequest(BaseModel):
    text: str


class SynthesizeResponse(BaseModel):
    audio: str  # base64-encoded WAV audio
    sample_rate: int


@app.post("/api/voice/synthesize", response_model=SynthesizeResponse)
async def voice_synthesize(request: SynthesizeRequest):
    """Synthesize text to audio using local Kokoro TTS model."""
    try:
        import base64
        import io
        import wave

        import numpy as np

        tts = _get_tts()
        audio_data, sample_rate = await asyncio.to_thread(tts.synthesize, request.text)

        # Encode audio as base64 WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            # Convert float32 to int16
            int16_data = (audio_data * 32767).astype(np.int16)
            wav_file.writeframes(int16_data.tobytes())

        wav_bytes = wav_buffer.getvalue()
        audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')

        return SynthesizeResponse(audio=audio_base64, sample_rate=sample_rate)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Synthesis error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")
