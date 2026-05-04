"""ASR module — Protocol + Qwen3 implementation.

Pure model inference, no microphone I/O.
"""

from __future__ import annotations

import numpy as np

from config.voice_game_config import EXIT_COMMANDS

# Combined exit commands: config-defined phrases plus shorthand aliases.
EXIT_SET = set(cmd.lower() for cmd in EXIT_COMMANDS) | {"q", "stop"}


class GameEndRequested(Exception):
    """Raised when the user requests to end the game."""

    pass


class Qwen3ASR:
    """Qwen3-ASR-0.6B wrapper.

    Uses ``qwen_asr.Qwen3ASRModel`` with local weights.
    The model handles resampling internally, so *audio* can be at any rate.
    """

    def __init__(self, model_path: str = "models/Qwen3-ASR-0.6B", device: str = "auto"):
        try:
            import torch
            from qwen_asr import Qwen3ASRModel

            self.model = Qwen3ASRModel.from_pretrained(
                model_path,
                dtype=torch.bfloat16,
                device_map=device,
            )
            # Print GPU device diagnostic
            _device = self.model.device if hasattr(self.model, 'device') else torch.device('cpu')
            _device_type = _device.type
            if _device_type == 'cuda':
                print(f"[ASR] Using CUDA GPU: {torch.cuda.get_device_name(0)}")
            elif _device_type == 'vulkan':
                print(f"[ASR] Using Vulkan GPU")
            else:
                print(f"[ASR] Running on CPU (no compatible GPU found)")
                print(f"[ASR] GPU acceleration requires PyTorch with CUDA or Vulkan backend.")
                print(f"[ASR] Check: torch.cuda.is_available()={torch.cuda.is_available()}")
            # Store device type for health reporting
            _device = self.model.device if hasattr(self.model, 'device') else torch.device('cpu')
            self.device_type = _device.type
            self.use_real_asr = True
            self.language = "English"  # Could be made configurable via voice.conf [asr] language
        except (ModuleNotFoundError, ImportError) as e:
            print(f"Note: Could not import qwen_asr ({e})")
            print("Using simple text-based ASR instead")
            self.device_type = "none"
            self.use_real_asr = False
            self.language = "English"
            self.model = None

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.use_real_asr and self.model:
            results = self.model.transcribe(audio=(audio, sample_rate), language=self.language)
            return results[0].text
        else:
            print("  (Simulating ASR - type your move instead of speaking)")
            try:
                user_input = input("Enter your move (e.g., 'center left'): ").strip()
                if user_input.lower() in EXIT_SET:
                    raise GameEndRequested("Game ended by user.")
                return user_input
            except EOFError:
                return "center"
