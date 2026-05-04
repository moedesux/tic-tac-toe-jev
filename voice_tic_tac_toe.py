"""Voice Tic-Tac-Toe — full speech pipeline.

Ties ASR, TextOrchestrator, and TTS together with push-to-talk mic/speaker I/O.

Usage:
    python voice_tic_tac_toe.py \\
        --slm-model model --slm-port 8080 --api-key "empty" \\
        --asr-model models/Qwen3-ASR-0.6B \\
        --tts-model models/kokoro-v1.0.onnx \\
        --device cuda:0 --debug
"""

from __future__ import annotations

import argparse

import numpy as np
import sounddevice as sd

from asr import Qwen3ASR, GameEndRequested
from config.config import get_voice_config
from voice_game_interface import VoiceGameInterface
from voice_game_orchestrator import SLMClient, TextOrchestrator
from tts import KokoroTTS

RECORD_SAMPLE_RATE = 16_000  # Hz, mono


class VoiceTicTacToe:
    """Push-to-talk voice loop: mic -> ASR -> orchestrator -> TTS -> speaker."""

    def __init__(
        self,
        asr: Qwen3ASR,
        orchestrator: TextOrchestrator,
        tts: KokoroTTS | None,
    ):
        self.asr = asr
        self.orchestrator = orchestrator
        self.tts = tts

    def record_utterance(self) -> tuple[np.ndarray, int]:
        """Record from the default mic until Enter is pressed.

        Uses a background ``sounddevice.InputStream`` so the main thread
        can simply block on ``input()``.
        """
        chunks: list[np.ndarray] = []

        def _callback(indata: np.ndarray, frames: int, time_info, status) -> None:
            if status:
                print(f"  [audio] {status}")
            chunks.append(indata.copy())

        stream = sd.InputStream(
            samplerate=RECORD_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=_callback,
        )

        input("  Press Enter to START recording...")
        stream.start()
        input("  Recording... Press Enter to STOP.")
        stream.stop()
        stream.close()

        if not chunks:
            return np.zeros(0, dtype=np.float32), RECORD_SAMPLE_RATE

        audio = np.concatenate(chunks, axis=0).squeeze()
        return audio, RECORD_SAMPLE_RATE

    @staticmethod
    def play_audio(audio: np.ndarray, sample_rate: int) -> None:
        """Play an audio array through the default speaker (blocking)."""
        sd.play(audio, samplerate=sample_rate)
        sd.wait()

    def run(self) -> None:
        """Main loop."""
        print("Voice Tic-Tac-Toe (push-to-talk - say 'quit' or 'exit' to stop)\n")

        try:
            while True:
                # 1. Record
                audio, sr = self.record_utterance()
                if audio.size == 0:
                    print("  (no audio captured, try again)")
                    continue

                # 2. ASR
                transcript = self.asr.transcribe(audio, sr)
                print(f"  You: {transcript}")

                if not transcript.strip():
                    print("  (empty transcript, try again)")
                    continue

                # 3. Orchestrator
                response = self.orchestrator.process_utterance(transcript)
                if response is None:
                    print("Bot: Thanks for playing Tic-Tac-Toe!")
                    break

                # 4. TTS + playback
                if self.tts:
                    tts_audio, tts_sr = self.tts.synthesize(response)
                    self.play_audio(tts_audio, tts_sr)
                else:
                    print(f"  Bot: {response}")

        except (KeyboardInterrupt, EOFError, GameEndRequested):
            print("\nBot: Thanks for playing Tic-Tac-Toe!")


# Emergency fallback defaults — only used when config loading fails entirely.
# Actual values are in config/voice.conf and loaded via VoiceConfig.
_DEFAULT_SLM_MODEL = "moe249/google_gemma-4-E4B-it-tictactoe"
_DEFAULT_SLM_PORT = 8080
_DEFAULT_API_KEY = "EMPTY"
_DEFAULT_ASR_MODEL = "models/Qwen3-ASR-0.6B"
_DEFAULT_TTS_MODEL = "models/kokoro-v1.0.onnx"
_DEFAULT_TTS_VOICES = "models/voices-v1.0.bin"
_DEFAULT_TTS_VOICE = "af_sarah"
_DEFAULT_TTS_SPEED = "1.0"
_DEFAULT_TTS_LANG = "en-us"


def _resolve_config_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Resolve CLI args against config.py defaults.

    Each argument that was passed on the command line (non-None) takes
    priority.  When None, the value is pulled from VoiceConfig.  If the
    config module is unavailable or a field is missing, the hardcoded
    fallback above is used.
    """
    try:
        vc = get_voice_config()
    except Exception:
        vc = None  # type: ignore[assignment]

    # SLM
    if args.slm_model is None:
        args.slm_model = vc.slm_model_name if vc is not None else _DEFAULT_SLM_MODEL
    if args.slm_port is None:
        args.slm_port = vc.slm_port if vc is not None else _DEFAULT_SLM_PORT
    if args.api_key is None:
        args.api_key = vc.slm_api_key if vc is not None else _DEFAULT_API_KEY

    # ASR
    if args.asr_model is None:
        args.asr_model = vc.asr_model_path if vc is not None else _DEFAULT_ASR_MODEL

    # TTS
    if args.tts_model is None:
        args.tts_model = vc.tts_model_path if vc is not None else _DEFAULT_TTS_MODEL
    if args.tts_voices is None:
        args.tts_voices = vc.tts_voices_path if vc is not None else _DEFAULT_TTS_VOICES
    if args.tts_voice is None:
        args.tts_voice = vc.tts_voice if vc is not None else _DEFAULT_TTS_VOICE
    if args.tts_speed is None:
        args.tts_speed = float(vc.tts_speed) if vc is not None else float(_DEFAULT_TTS_SPEED)
    if args.tts_lang is None:
        args.tts_lang = vc.tts_lang if vc is not None else _DEFAULT_TTS_LANG

    return args


def _validate_config(args: argparse.Namespace, tts_enabled: bool = True) -> None:
    """Validate that required packages and model paths are available. Exit with error if not."""
    from pathlib import Path

    # 1. Strict mode: require qwen_asr and kokoro_onnx
    try:
        import qwen_asr  # noqa: F401
    except ImportError:
        print("ERROR: qwen_asr package is not installed.")
        print("Install it with: uv pip install qwen_asr")
        exit(1)

    if tts_enabled:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            print("ERROR: kokoro_onnx package is not installed.")
            print("Install it with: uv pip install kokoro_onnx")
            exit(1)

    # 2. Validate model paths exist on disk
    if not Path(args.asr_model).is_dir():
        print(f"ERROR: --asr-model path does not exist: {args.asr_model}")
        exit(1)
    if tts_enabled:
        if not Path(args.tts_model).is_file():
            print(f"ERROR: --tts-model path does not exist: {args.tts_model}")
            exit(1)
        if not Path(args.tts_voices).is_file():
            print(f"ERROR: --tts-voices path does not exist: {args.tts_voices}")
            exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Tic-Tac-Toe")

    # SLM / orchestrator
    parser.add_argument(
        "--slm-model",
        type=str,
        default=None,
        help="Model name served by the SLM backend",
    )
    parser.add_argument(
        "--slm-port", type=int, default=None, help="Port of the SLM server"
    )
    parser.add_argument(
        "--api-key", type=str, default=None, help="API key for SLM server"
    )

    # ASR
    parser.add_argument(
        "--asr-model",
        type=str,
        default=None,
        help="Path to ASR model weights",
    )

    # TTS
    parser.add_argument(
        "--tts-model",
        type=str,
        default=None,
        help="Path to Kokoro ONNX model file",
    )
    parser.add_argument(
        "--tts-voices",
        type=str,
        default=None,
        help="Path to Kokoro voices ONNX file",
    )
    parser.add_argument(
        "--tts-voice",
        type=str,
        default=None,
        help="Kokoro voice name (default: af_sarah)",
    )
    parser.add_argument(
        "--tts-speed",
        type=float,
        default=None,
        help="Kokoro speech speed multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--tts-lang",
        type=str,
        default=None,
        help="Kokoro language code (default: en-us)",
    )

    # Shared
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Torch device for ASR/TTS models",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print raw SLM output each turn"
    )
    args = parser.parse_args()

    # --- Resolve CLI args against config defaults ---
    args = _resolve_config_defaults(args)

    # Check TTS config before validation
    try:
        vc = get_voice_config()
        tts_enabled = vc.tts_enabled
    except Exception:
        tts_enabled = True  # default to enabled if config unavailable

    # --- Validate config ---
    _validate_config(args, tts_enabled=tts_enabled)

    # --- Build components ---
    print("Loading ASR model...")
    asr = Qwen3ASR(model_path=args.asr_model, device=args.device)

    if not tts_enabled:
        print("TTS disabled — responses will be printed to console only")
        tts = None
    else:
        print("Loading TTS model...")
        tts = KokoroTTS(
            model_path=args.tts_model,
            voices_path=args.tts_voices,
            voice=args.tts_voice,
            speed=args.tts_speed,
            lang=args.tts_lang,
        )

    game = VoiceGameInterface()
    slm = SLMClient(model_name=args.slm_model, api_key=args.api_key, port=args.slm_port)
    orchestrator = TextOrchestrator(slm, game, debug=args.debug)

    # --- Run ---
    game_voice = VoiceTicTacToe(asr=asr, orchestrator=orchestrator, tts=tts)
    game_voice.run()


if __name__ == "__main__":
    main()
