"""Settings dialog tests."""

from __future__ import annotations

from naji.config import DEFAULT_INSTRUCTIONS, Config
from naji.i18n import Translator
from naji.ui.settings import SettingsDialog


def test_settings_save_updates_runtime_config(qapp) -> None:
    config = Config()
    dialog = SettingsDialog(config, Translator("en"))
    saved: list[bool] = []
    dialog.saved.connect(lambda: saved.append(True))
    try:
        dialog._theme.setCurrentIndex(dialog._theme.findData("light"))
        dialog._locale.setCurrentIndex(dialog._locale.findData("pt-BR"))
        dialog._auto_hide.setValue(12000)
        dialog._reduced_motion.setChecked(True)
        dialog._save()

        assert saved == [True]
        assert config.ui.theme == "light"
        assert config.ui.locale == "pt-BR"
        assert config.ui.auto_hide_ms == 12000
        assert config.ui.reduced_motion is True
    finally:
        dialog.deleteLater()
        qapp.processEvents()


def test_settings_save_speech_mode_and_instructions(qapp) -> None:
    config = Config()
    dialog = SettingsDialog(config, Translator("pt-BR"))
    try:
        dialog._speech_mode.setCurrentIndex(dialog._speech_mode.findData("vad"))
        dialog._instructions.setPlainText("  Responda sempre em inglês.  ")
        dialog._save()

        assert config.ui.speech_mode == "vad"
        assert config.models.instructions == "Responda sempre em inglês."

        dialog._instructions.setPlainText("   ")
        dialog._save()
        assert config.models.instructions == DEFAULT_INSTRUCTIONS
    finally:
        dialog.deleteLater()
        qapp.processEvents()
