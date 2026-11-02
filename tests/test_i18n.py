"""Translation tests."""

from __future__ import annotations

from naji.i18n import Translator, normalize_locale, resolve_locale
from naji.i18n.en import STRINGS as EN
from naji.i18n.pt_br import STRINGS as PT_BR


def test_locale_parity() -> None:
    assert set(PT_BR) == set(EN)
    assert all(value for value in PT_BR.values())
    assert all(value for value in EN.values())


def test_normalize_locale() -> None:
    assert normalize_locale("pt_BR") == "pt-BR"
    assert normalize_locale("pt") == "pt-BR"
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("de") is None


def test_translator_and_fallback() -> None:
    assert Translator("pt-BR").t("tray.quit") == "Sair"
    assert Translator("en").t("tray.quit") == "Quit"
    assert Translator("pt-BR").t("missing.key") == "missing.key"
    hint = Translator("pt-BR").t("bar.summoned.hint", hotkey="Ctrl+Alt+Space")
    assert "Ctrl+Alt+Space" in hint


def test_resolve_explicit_locale() -> None:
    assert resolve_locale("en") == "en"
    assert resolve_locale("pt-BR") == "pt-BR"
