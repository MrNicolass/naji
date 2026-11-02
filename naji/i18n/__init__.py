"""Small translation layer (PT-BR + English).

The UI never hardcodes user-facing text. Keys are flat strings so the
dictionaries are easy to diff and test for parity.
"""

from __future__ import annotations

import os
from typing import Any

from naji.i18n.en import STRINGS as EN
from naji.i18n.pt_br import STRINGS as PT_BR

SUPPORTED_LOCALES = ("pt-BR", "en")
DEFAULT_LOCALE = "pt-BR"
_TABLES = {"pt-BR": PT_BR, "en": EN}


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.replace("_", "-").strip().lower()
    if normalized.startswith("pt"):
        return "pt-BR"
    if normalized.startswith("en"):
        return "en"
    return None


def _windows_locale() -> str | None:
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return None
    primary = langid & 0x3FF
    if primary == 0x16:
        return "pt-BR"
    if primary == 0x09:
        return "en"
    return None


def system_locale() -> str:
    if os.name == "nt":
        return _windows_locale() or DEFAULT_LOCALE
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        resolved = normalize_locale(os.environ.get(variable))
        if resolved:
            return resolved
    try:
        import locale

        resolved = normalize_locale(locale.getlocale()[0])
        if resolved:
            return resolved
    except Exception:
        pass
    return DEFAULT_LOCALE


def resolve_locale(value: str | None) -> str:
    if value and value != "system":
        resolved = normalize_locale(value)
        if resolved:
            return resolved
    return system_locale()


class Translator:
    """Resolve keys for the active locale with English fallback."""

    def __init__(self, locale: str | None = "system") -> None:
        self._locale = resolve_locale(locale)

    @property
    def locale(self) -> str:
        return self._locale

    def set_locale(self, locale: str) -> None:
        self._locale = resolve_locale(locale)

    def t(self, key: str, **kwargs: Any) -> str:
        table = _TABLES[self._locale]
        text = table.get(key) or EN.get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text


__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "Translator",
    "normalize_locale",
    "resolve_locale",
    "system_locale",
]
