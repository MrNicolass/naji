"""Screen capture tool for the model tool registry.

Captures the primary screen with PySide6 (no extra dependency) and saves a
PNG next to the other Naji data. The tool is safe: it only reads the screen
and writes a file inside the Naji data directory.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path


def get_screenshot_dir() -> Path:
    """Return the directory where screenshots are stored."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "Naji" / "screenshots"


def _unique_target(directory: Path, stamp: str) -> Path:
    target = directory / f"naji_screenshot_{stamp}.png"
    counter = 1
    while target.exists():
        target = directory / f"naji_screenshot_{stamp}_{counter}.png"
        counter += 1
    return target


async def take_screenshot() -> str:
    """Capture the primary screen and save it as PNG. Returns the file path."""
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return "Error: screen capture is not available on this platform."

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return "Error: no screen available to capture."

    pixmap = screen.grabWindow(0)
    if pixmap.isNull():
        return "Error: screen capture failed."

    directory = get_screenshot_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = _unique_target(directory, datetime.now().strftime("%Y%m%d_%H%M%S"))
        if not pixmap.save(str(target), "PNG"):
            return "Error: could not save the screenshot."
    except OSError as exc:
        return f"Error: could not save the screenshot: {exc}"
    return str(target)


def get_screenshot_schema() -> dict:
    """Return the OpenAI function-calling schema for the screenshot tool."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="take_screenshot",
        description=(
            "Capture the primary screen and save it as a PNG image. "
            "Returns the saved file path. Use it when the user asks to take "
            "a screenshot or capture the screen."
        ),
        parameters={},
    )
