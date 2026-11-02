"""Bar smoke tests (offscreen)."""

from __future__ import annotations

from naji.config import Config
from naji.i18n import Translator
from naji.ui.bar import NajiBar, format_hotkey
from naji.ui.theme import get_tokens


def test_format_hotkey() -> None:
    assert format_hotkey("ctrl+alt+space") == "Ctrl+Alt+Space"
    assert format_hotkey("F1") == "F1"


def test_bar_states(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.set_state("listening")
        assert bar.state == "listening"

        bar.show_bar("summoned")
        assert bar.isVisible()
        assert bar.state == "summoned"

        bar.hide_bar()
        qapp.processEvents()
        assert not bar.isVisible()
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_expands_for_session_history(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.set_history(
            [
                {"role": "user", "content": "Que horas são?"},
                {"role": "assistant", "content": "São dez horas."},
                {"role": "tool", "content": "ignored"},
            ]
        )
        bar.show_bar()
        bar.toggle_history()

        assert bar.history_visible
        assert bar.height() > 96

        bar.toggle_history()
        assert not bar.history_visible
        assert bar.height() > 96
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_submits_typed_text(qapp) -> None:
    config = Config()
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    submitted: list[str] = []
    bar.text_submitted.connect(submitted.append)
    try:
        bar._text_input.setText("  olá, Naji  ")
        bar._text_input.returnPressed.emit()

        assert submitted == ["olá, Naji"]
        assert bar._text_input.text() == ""

        bar.set_state("thinking")
        bar._text_input.setText("não envia")
        bar._text_input.returnPressed.emit()
        assert submitted == ["olá, Naji"]
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_does_not_auto_hide_while_typing(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    config.ui.auto_hide_ms = 1500
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.show_bar("summoned")
        assert bar._hide_timer.isActive()

        bar._text_input.setFocus()
        bar._text_input.setText("digitando")
        qapp.processEvents()
        assert not bar._hide_timer.isActive()

        bar._text_input.clear()
        bar._text_input.clearFocus()
        qapp.processEvents()
        assert bar._hide_timer.isActive()
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_hints_follow_speech_mode(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.show_bar("summoned")
        assert "Segure" in bar._hint.text()

        config.ui.speech_mode = "vad"
        bar.show_bar("summoned")
        assert "terminar" in bar._hint.text()

        bar.set_state("listening")
        assert "parar de falar" in bar._hint.text()

        config.ui.speech_mode = "toggle"
        bar.set_state("listening")
        assert "Pressione" in bar._hint.text()
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_controls_accept_keyboard_focus(qapp) -> None:
    bar = NajiBar(Config(), Translator("pt-BR"), get_tokens("dark"))
    try:
        controls = (
            bar._stop_btn,
            bar._mute_btn,
            bar._history_btn,
            bar._new_btn,
            bar._settings_btn,
            bar._close_btn,
            bar._send_btn,
        )
        assert all(button.focusPolicy().name == "StrongFocus" for button in controls)
        assert all(button.toolTip() for button in controls)
        assert bar._text_input.nextInFocusChain() is bar._send_btn
        assert bar._send_btn.nextInFocusChain() is bar._mute_btn
    finally:
        bar.deleteLater()
        qapp.processEvents()


_BUTTONS = (
    "_stop_btn",
    "_mute_btn",
    "_history_btn",
    "_new_btn",
    "_settings_btn",
    "_close_btn",
    "_send_btn",
)


def test_bar_reopen_summoned_focuses_input_not_button(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.show_bar("summoned")
        bar._close_btn.setFocus()
        assert bar.focusWidget() is bar._close_btn
        bar.hide_bar()
        qapp.processEvents()

        bar.show_bar("summoned")
        qapp.processEvents()

        assert bar.focusWidget() is bar._text_input
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_show_listening_clears_stale_button_focus(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.show_bar("summoned")
        bar._close_btn.setFocus()
        assert bar.focusWidget() is bar._close_btn
        bar.hide_bar()
        qapp.processEvents()

        bar.show_bar("listening")
        qapp.processEvents()

        focused = bar.focusWidget()
        assert focused is not None
        assert all(focused is not getattr(bar, name) for name in _BUTTONS)
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_show_summoned_focuses_input(qapp) -> None:
    config = Config()
    config.ui.reduced_motion = True
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    try:
        bar.show_bar("summoned")
        qapp.processEvents()
        assert bar.focusWidget() is bar._text_input
    finally:
        bar.deleteLater()
        qapp.processEvents()


def test_bar_answers_inline_confirmation(qapp) -> None:
    config = Config()
    bar = NajiBar(config, Translator("pt-BR"), get_tokens("dark"))
    answers: list[bool] = []
    bar.confirmation_answered.connect(answers.append)
    try:
        bar.show_confirmation("Desligar o computador?")

        assert bar._confirmation_visible
        assert not bar._confirm_btn.isHidden()
        assert bar._text_input.isHidden()

        bar._deny_btn.click()

        assert answers == [False]
        assert not bar._confirmation_visible
        assert bar._deny_btn.isHidden()
    finally:
        bar.deleteLater()
        qapp.processEvents()
