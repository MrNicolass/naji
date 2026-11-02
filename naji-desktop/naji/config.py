"""Configuração do Naji (Pydantic Settings v2)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerConfig(BaseSettings):
    """Configuração de conexão com servidores llama.cpp."""

    model_config = SettingsConfigDict(env_prefix="NAJI_SERVER_", extra="ignore")

    voice_endpoint: str = Field(
        default="http://xserver:9931/v1",
        description="Endpoint do modelo de voz (WS /v1/realtime + /tts)",
    )
    executor_endpoint: str = Field(
        default="http://xserver:9931/v1",
        description="Endpoint do modelo executor (HTTP /v1/chat/completions)",
    )
    api_key: str | None = Field(
        default=None,
        description="API key (opcional). Se não definido, usa 'sk-no-key-required'.",
    )

    @field_validator("voice_endpoint", "executor_endpoint", mode="before")
    @classmethod
    def _normalize_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = "http://" + v
        if not v.endswith("/v1"):
            v = v.rstrip("/") + "/v1"
        return v


class ModelsConfig(BaseSettings):
    """Configuração dos modelos."""

    model_config = SettingsConfigDict(env_prefix="NAJI_MODELS_", extra="ignore")

    voice_model: str = Field(default="default", description="Nome do modelo de voz (router mode)")
    executor_model: str = Field(default="default", description="Nome do modelo executor (router mode)")
    same_model: bool = Field(
        default=True,
        description="Se True, usa o mesmo endpoint/modelo para voz e executor (modo único).",
    )


class AudioConfig(BaseSettings):
    """Configuração de áudio."""

    model_config = SettingsConfigDict(env_prefix="NAJI_AUDIO_", extra="ignore")

    sample_rate_in: int = Field(default=16000, description="Taxa de amostragem de entrada (captura)")
    sample_rate_out: int = Field(default=24000, description="Taxa de amostragem de saída (playback)")
    vad_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Threshold do VAD (0.0-1.0)"
    )
    barge_in_enabled: bool = Field(default=True, description="Habilita interrupção por VAD durante playback")
    vad_min_speech_ms: int = Field(default=180, description="Duração mínima de fala para commit (ms)")
    vad_pre_roll_ms: int = Field(default=500, description="Pré-roll antes da fala detectada (ms)")
    jitter_buffer_ms: int = Field(default=100, description="Buffer de jitter para playback (ms)")
    chunk_ms: int = Field(default=30, description="Tamanho do chunk de áudio capturado (ms)")


class UIConfig(BaseSettings):
    """Configuração da interface."""

    model_config = SettingsConfigDict(env_prefix="NAJI_UI_", extra="ignore")

    theme: Literal["dark"] = "dark"
    hotkey: str = Field(default="ctrl+alt+space", description="Hotkey global para PTT")
    start_minimized: bool = Field(default=False)
    show_tray: bool = Field(default=True)


class ToolsConfig(BaseSettings):
    """Configuração de ferramentas nativas."""

    model_config = SettingsConfigDict(env_prefix="NAJI_TOOLS_", extra="ignore")

    enabled: list[str] = Field(
        default_factory=lambda: ["media_control", "weather", "datetime", "web_search"],
        description="Lista de ferramentas habilitadas",
    )
    weather_unit: Literal["celsius", "fahrenheit"] = "celsius"
    web_search_max_results: int = Field(default=5, ge=1, le=10)


class Config(BaseSettings):
    """Configuração raiz do Naji."""

    model_config = SettingsConfigDict(
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

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> Config:
        """Carrega configuração de YAML + env + defaults."""
        data = {}
        if config_path:
            path = Path(config_path)
            if path.exists():
                import yaml
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(**data)

    def save_yaml(self, path: str | Path) -> None:
        """Salva configuração atual em YAML (sem api_key)."""
        import yaml
        data = self.model_dump(mode="python")
        # Remove api_key do YAML salvo
        if "server" in data and "api_key" in data["server"]:
            data["server"]["api_key"] = None
        Path(path).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def get_config_dir() -> Path:
    """Retorna o diretório de configuração do usuário."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Naji"


def get_default_config_path() -> Path:
    return get_config_dir() / "config.yaml"


def load_config(config_path: str | Path | None = None) -> Config:
    """Carrega configuração do caminho padrão ou informado."""
    path = config_path or get_default_config_path()
    return Config.load(path)
