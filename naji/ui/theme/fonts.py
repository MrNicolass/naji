"""Bundled application font registration."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase, QGuiApplication

from naji.paths import asset_path

_FONT_FILES = ("Geist.ttf", "GeistMono.ttf")


def load_application_fonts() -> tuple[str, ...]:
    """Register bundled fonts after the Qt application is initialized.

    Application fonts do not alter the host system and are available to the
    source checkout as well as the PyInstaller onefile extraction directory.
    """
    if QGuiApplication.instance() is None:
        return ()

    families: list[str] = []
    for filename in _FONT_FILES:
        font_id = QFontDatabase.addApplicationFont(str(asset_path("fonts", filename)))
        if font_id >= 0:
            for family in QFontDatabase.applicationFontFamilies(font_id):
                if family not in families:
                    families.append(family)
    return tuple(families)
