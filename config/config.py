"""Backend and voice game configuration.

Located in the config/ directory. All config file resolution uses
this file's location as the base, ensuring stable paths regardless of
where the invoking script runs from.

Voice game settings are loaded from voice_game_config.py as Python constants
(clean triple-quoted strings). Infrastructure settings (SLM, ASR, TTS) are
still loaded from voice.conf for backwards compatibility with startup scripts.
"""

import configparser
from pathlib import Path

# Import all voice game constants from the dedicated module
from config.voice_game_config import (
    GAME_TOOLS,
    GAME_TOOLS_SLOT_DESCRIPTIONS,
    EXIT_COMMANDS,
    CLARIFICATION_CAPABILITIES,
    ROW_NAMES,
    COL_NAMES,
    POSITION_MAPPINGS,
    SLOT_REQUIREMENTS,
    SLOT_PROMPTS,
    SUCCESS_TEMPLATES,
    SYSTEM_PROMPT,
)


# Get the project root directory — use this file's location for stable resolution
PROJECT_ROOT = Path(__file__).parent


class BackendConfig:
    """Configuration for the backend server."""

    def __init__(self):
        self.config_path = PROJECT_ROOT / "backend.conf"
        self.config = configparser.ConfigParser()
        self.config.read(self.config_path)

    @property
    def host(self) -> str:
        return self.config.get("server", "HOST").strip('"')

    @property
    def port(self) -> int:
        return self.config.getint("server", "PORT")

    @property
    def api_title(self) -> str:
        return self.config.get("server", "API_TITLE").strip('"')

    @property
    def api_version(self) -> str:
        return self.config.get("server", "API_VERSION").strip('"')


class VoiceConfig:
    """Configuration for the voice game orchestrator.

    Voice game settings come from voice_game_config.py (Python constants).
    Infrastructure settings (SLM, ASR, TTS) still come from voice.conf.
    """

    def __init__(self):
        self.config_path = PROJECT_ROOT / "voice.conf"
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.read(self.config_path)

    # --- Infrastructure settings (from voice.conf) ---

    @property
    def slm_host(self) -> str:
        return self.config.get("slm", "host").strip('"')

    @property
    def slm_port(self) -> int:
        return self.config.getint("slm", "port")

    @property
    def slm_api_key(self) -> str:
        return self.config.get("slm", "api_key").strip('"')

    @property
    def slm_model_name(self) -> str:
        return self.config.get("slm", "model_name").strip('"')

    @property
    def slm_model_path(self) -> str:
        return self.config.get("slm", "model_path").strip('"')

    @property
    def asr_model_path(self) -> str:
        return self.config.get("asr", "model_path").strip('"')

    @property
    def tts_model_path(self) -> str:
        return self.config.get("tts", "model_path").strip('"')

    @property
    def tts_voices_path(self) -> str:
        return self.config.get("tts", "voices_path").strip('"')

    @property
    def tts_voice(self) -> str:
        return self.config.get("tts", "voice").strip('"')

    @property
    def tts_speed(self) -> float:
        return float(self.config.get("tts", "speed").strip('"'))

    @property
    def tts_lang(self) -> str:
        return self.config.get("tts", "lang").strip('"')

    @property
    def tts_sample_rate(self) -> int:
        return self.config.getint("tts", "sample_rate", fallback=24000)

    @property
    def api_base_url(self) -> str:
        return self.config.get("api_gateway", "base_url").strip('"')

    @property
    def tts_enabled(self) -> bool:
        """Whether TTS playback is enabled."""
        return self.config.getboolean("tts", "enabled", fallback=True)


# Module-level singletons
_voice_config = VoiceConfig()
_backend_config = BackendConfig()


def get_voice_config() -> VoiceConfig:
    """Get the voice configuration singleton."""
    return _voice_config


def get_backend_config() -> BackendConfig:
    """Get the backend configuration singleton."""
    return _backend_config
