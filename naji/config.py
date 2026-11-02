"""Configuration for Naji (Pydantic Settings v2).

The desktop app is tray-first: a single process owns the tray icon, the global
hotkey and the floating bar. Configuration is loaded from YAML, then overridden
by environment variables (for example ``NAJI_SERVER__API_KEY``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INSTRUCTIONS = (
    "Você é Naji, um assistente de voz conciso que roda no desktop do usuário. "
    "Responda sempre em português do Brasil, de forma curta, natural e direta, "
    "como uma resposta falada. Não use formatação markdown, listas, títulos, "
    "negrito ou emojis. Use as ferramentas fornecidas para executar ações e "
    "para buscar informações atuais (notícias, clima, cotações, horários); "
    "nunca invente fatos, resultados ou notícias. Nunca diga que uma ação foi "
    "feita se a ferramenta não retornou sucesso."
)

DEFAULT_TOOLS = [
    "media_control",
    "volume_control",
    "notification",
    "timer_control",
    "weather",
    "datetime",
    "web_search",
    "screenshot",
    "app_control",
    "power_control",
    "window_control",
    "file_control",
]


class ServerConfig(BaseModel):
    """Connections to llama.cpp servers."""

    model_config = ConfigDict(extra="ignore")

    voice_endpoint: str = Field(
        default="http://xserver:9931/v1",
        description="Voice endpoint (WS /v1/realtime + /tts + /transcribe).",
    )
    executor_endpoint: str = Field(
        default="http://xserver:9931/v1",
        description="Executor endpoint (HTTP /v1/chat/completions).",
    )
    api_key: str | None = Field(
        default=None,
        description="Optional API key. Falls back to 'sk-no-key-required'.",
    )
    request_timeout_s: float = Field(default=30.0, gt=0, le=300)
    transcribe_timeout_s: float = Field(default=120.0, gt=0, le=600)

    @field_validator("voice_endpoint", "executor_endpoint", mode="before")
    @classmethod
    def _normalize_url(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("endpoint cannot be empty")
        if not value.startswith(("http://", "https://")):
            value = "http://" + value
        value = value.rstrip("/")
        if not value.endswith("/v1"):
            value = value + "/v1"
        return value


class ModelsConfig(BaseModel):
    """Model selection.

    ``mode='single'`` uses one omni model for voice and chat. ``mode='dual'``
    allows a dedicated executor model. The legacy ``same_model`` key is migrated
    automatically by :meth:`Config.load`.
    """

    model_config = ConfigDict(extra="ignore")

    mode: Literal["single", "dual"] = Field(
        default="single",
        description="single = one omni model; dual = voice + executor.",
    )
    voice_model: str = Field(default="default", description="Voice model name (router mode).")
    executor_model: str = Field(default="default", description="Executor model name (router mode).")
    instructions: str = Field(default=DEFAULT_INSTRUCTIONS, description="System prompt.")

    @property
    def same_model(self) -> bool:
        """Backward-compatible view of the old ``same_model`` flag."""
        return self.mode == "single"


class AudioConfig(BaseModel):
    """Audio capture, playback and VAD."""

    model_config = ConfigDict(extra="ignore")

    sample_rate_in: int = Field(default=16000, description="Capture rate (Hz).")
    sample_rate_out: int = Field(default=24000, description="Playback rate (Hz).")
    input_device: int | None = Field(default=None, description="sounddevice input index.")
    output_device: int | None = Field(default=None, description="sounddevice output index.")
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    barge_in_enabled: bool = Field(default=True)
    vad_min_speech_ms: int = Field(default=180, ge=0)
    vad_silence_ms: int = Field(default=700, ge=100, le=5000)
    vad_pre_roll_ms: int = Field(default=500, ge=0)
    jitter_buffer_ms: int = Field(default=100, ge=0)
    chunk_ms: int = Field(default=30, ge=10, le=200)
    min_record_ms: int = Field(default=300, ge=100, le=2000)
    max_record_s: int = Field(default=60, ge=5, le=300)


class UIConfig(BaseModel):
    """Bar, tray, hotkey and theme."""

    model_config = ConfigDict(extra="ignore")

    theme: Literal["system", "dark", "light"] = "system"
    locale: Literal["system", "pt-BR", "en"] = "system"
    hotkey: str = Field(default="ctrl+alt+space", description="Global push-to-talk hotkey.")
    speech_mode: Literal["ptt", "toggle", "vad"] = "ptt"
    auto_hide_ms: int = Field(default=8000, ge=1000, le=60000)
    follow_up_ms: int = Field(default=6000, ge=1000, le=60000)
    history_enabled: bool = True
    reduced_motion: bool = False
    start_with_windows: bool = False
    start_minimized: bool = True
    show_tray: bool = True


class ToolsConfig(BaseModel):
    """Built-in tools."""

    model_config = ConfigDict(extra="ignore")

    enabled: list[str] = Field(default_factory=lambda: list(DEFAULT_TOOLS))
    weather_unit: Literal["celsius", "fahrenheit"] = "celsius"
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    tool_loop_limit: int = Field(default=4, ge=1, le=8)


class WakeConfig(BaseModel):
    """Wake word (openWakeWord).

    ``word`` is a built-in model name (``hey_jarvis``, ``alexa``,
    ``hey_mycroft``) or a path to a custom ``.onnx`` model.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    word: str = "hey_jarvis"
    threshold: float = Field(default=0.4, ge=0.05, le=1.0)


class Config(BaseSettings):
    """Root configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NAJI_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    wake: WakeConfig = Field(default_factory=WakeConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """Load YAML, then apply environment overrides and defaults."""
        data: dict = {}
        if config_path:
            path = Path(config_path)
            if path.exists():
                import yaml

                loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if not isinstance(loaded, dict):
                    raise ValueError(f"config file must contain a mapping: {path}")
                data = loaded

        models = data.get("models")
        if isinstance(models, dict) and "same_model" in models and "mode" not in models:
            models["mode"] = "single" if models.pop("same_model") else "dual"

        return cls(**data)

    def save_yaml(self, path: str | Path) -> None:
        """Write the current configuration, never persisting the API key."""
        import yaml

        data = self.model_dump(mode="python")
        data.setdefault("server", {})["api_key"] = None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def get_config_dir() -> Path:
    """Return the per-user configuration directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Naji"


def get_log_dir() -> Path:
    return get_config_dir() / "logs"


def get_default_config_path() -> Path:
    return get_config_dir() / "config.yaml"


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from the default or given path."""
    return Config.load(config_path or get_default_config_path())


def load_or_create_config(config_path: str | Path | None = None) -> tuple[Config, Path]:
    """Load configuration, creating the default file on first run."""
    path = Path(config_path) if config_path else get_default_config_path()
    if not path.exists():
        config = Config()
        config.save_yaml(path)
        return config, path
    return Config.load(path), path
