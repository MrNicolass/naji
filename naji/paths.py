"""Filesystem paths used by the packaged and source builds."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Return the directory that contains runtime assets.

    PyInstaller onefile extracts data into ``sys._MEIPASS``. In a source
    checkout, assets live next to the ``naji`` package (repository root).
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def asset_path(*parts: str) -> Path:
    return app_root().joinpath("assets", *parts)
