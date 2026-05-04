"""TTS module — Protocol + Kokoro ONNX implementation.

Pure model inference, no speaker I/O.
"""

from __future__ import annotations

import numpy as np

from config.config import get_voice_config


class KokoroTTS:
    """Kokoro-82M ONNX TTS wrapper.

    Uses ``kokoro_onnx.Kokoro`` with local ONNX model weights.
    Runs on CPU or GPU (Vulkan/CUDA) via ONNX Runtime.
    Sample rate: 24 kHz.
    """

    def __init__(
        self,
        model_path: str = "models/kokoro-v1.0.onnx",
        voices_path: str = "models/voices-v1.0.bin",
        voice: str = "af_sarah",
        speed: float = 1.0,
        lang: str = "en-us",
    ):
        self.model_path = model_path
        self.voices_path = voices_path
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self.device_type = "none"
        self.use_real_tts = False
        self.model = None

        try:
            from kokoro_onnx import Kokoro

            self.model = Kokoro(model_path, voices_path)

            # Detect device from ONNX Runtime
            try:
                import onnxruntime as ort
                providers = ort.get_available_providers()
                if "CUDAExecutionProvider" in providers:
                    self.device_type = "cuda"
                    print(f"[TTS] Using CUDA GPU via ONNX Runtime")
                elif "VulkanExecutionProvider" in providers:
                    self.device_type = "vulkan"
                    print(f"[TTS] Using Vulkan GPU via ONNX Runtime")
                else:
                    self.device_type = "cpu"
                    print(f"[TTS] Running on CPU via ONNX Runtime")
                    print(f"[TTS] Available providers: {providers}")
            except ImportError:
                self.device_type = "cpu"
                print(f"[TTS] Running on CPU (ONNX Runtime available)")

            # Validate voice
            try:
                voices = list(self.model.get_voices())
                if self.voice not in voices:
                    print(f"[TTS] Voice '{self.voice}' not found, using 'af_sarah'")
                    self.voice = "af_sarah"
                self.use_real_tts = True
            except Exception as e:
                print(f"[TTS] Voice validation failed: {e}")
                self.use_real_tts = False

        except FileNotFoundError as e:
            print(f"[TTS] Model files not found: {e}")
            print(f"[TTS] Download from: https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/")
            print("Using text-only output instead of TTS")
        except (ModuleNotFoundError, ImportError) as e:
            print(f"[TTS] Could not import kokoro_onnx ({e})")
            print("Using text-only output instead of TTS")

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        if self.use_real_tts and self.model:
            samples, sample_rate = self.model.create(
                text, voice=self.voice, speed=self.speed, lang=self.lang
            )
            # kokoro_onnx returns list[float]; convert to numpy float32
            audio_data = np.array(samples, dtype=np.float32)
            return audio_data, sample_rate
        else:
            # Return dummy audio with text for text-only mode
            vc = get_voice_config()
            sample_rate = vc.tts_sample_rate
            audio = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
            print(f"  Bot: {text}")
            return audio, sample_rate
