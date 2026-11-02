"""Configuration tests (offline)."""

from __future__ import annotations

from pathlib import Path

import yaml

from naji.config import Config, ServerConfig, load_or_create_config


def test_defaults() -> None:
    config = Config()
    assert config.models.mode == "single"
    assert config.models.same_model is True
    assert config.ui.theme == "system"
    assert config.ui.start_minimized is True
    assert config.tools.tool_loop_limit == 4
    assert config.wake.enabled is False


def test_url_normalization() -> None:
    assert ServerConfig(voice_endpoint="xserver:9931").voice_endpoint == ("http://xserver:9931/v1")
    assert ServerConfig(executor_endpoint="https://host/v1/").executor_endpoint == (
        "https://host/v1"
    )


def test_legacy_same_model_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({"models": {"same_model": False}}),
        encoding="utf-8",
    )
    config = Config.load(path)
    assert config.models.mode == "dual"
    assert config.models.same_model is False


def test_save_omits_api_key(tmp_path: Path) -> None:
    config = Config()
    config.server.api_key = "super-secret"
    path = tmp_path / "config.yaml"
    config.save_yaml(path)

    text = path.read_text(encoding="utf-8")
    assert "super-secret" not in text
    assert Config.load(path).server.api_key is None


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("NAJI_UI__HOTKEY", "ctrl+shift+space")
    monkeypatch.setenv("NAJI_SERVER__API_KEY", "from-env")
    config = Config()
    assert config.ui.hotkey == "ctrl+shift+space"
    assert config.server.api_key == "from-env"


def test_load_or_create_writes_defaults(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "config.yaml"
    config, resolved = load_or_create_config(path)
    assert resolved == path
    assert path.exists()
    assert config.server.api_key is None
