"""App launch and close controls for the model tool registry.

Opening an app is a safe action. Closing an app is destructive (unsaved work
may be lost) and is registered as a dangerous tool that requires explicit
confirmation in the bar before it runs.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

_APPS = {
    "notepad": {
        "win32": ["notepad.exe"],
        "linux": ["gedit", "kate", "mousepad", "xed"],
    },
    "terminal": {
        "win32": ["cmd.exe"],
        "linux": ["gnome-terminal", "konsole", "xterm", "alacritty", "kitty"],
    },
    "calculator": {
        "win32": ["calc.exe"],
        "linux": ["gnome-calculator", "kcalc", "qalculate-gtk"],
    },
    "browser": {
        "win32": ["msedge.exe", "chrome.exe", "firefox.exe"],
        "linux": ["firefox", "chromium", "google-chrome", "brave-browser"],
    },
    "settings": {
        "win32": ["ms-settings:"],
        "linux": ["gnome-control-center", "systemsettings", "xfce4-settings-manager"],
    },
    "explorer": {
        "win32": ["explorer.exe"],
        "linux": ["nautilus", "dolphin", "thunar", "pcmanfm"],
    },
}


def _resolve_app(app_key: str) -> list[str] | None:
    platform = "win32" if sys.platform == "win32" else "linux"
    entry = _APPS.get(app_key)
    if not entry:
        return None
    return entry.get(platform) or entry.get("linux") or []


async def app_open(app: str) -> str:
    """Launch a predefined system application."""
    targets = _resolve_app(app)
    if not targets:
        return f"Error: unknown application '{app}'"
    return await _open_app(targets)


async def app_close(app: str) -> str:
    """Close a predefined system application. Requires user confirmation."""
    targets = _resolve_app(app)
    if not targets:
        return f"Error: unknown application '{app}'"
    return await _close_app(app, targets)


async def _open_app(candidates: list[str]) -> str:
    """Launch the first available candidate."""
    if sys.platform == "win32":
        for cmd in candidates:
            try:
                if cmd.endswith(":"):
                    subprocess.Popen(["cmd", "/c", "start", "", cmd], shell=True)
                else:
                    subprocess.Popen([cmd])
                return f"Opened {cmd}."
            except Exception:
                continue
        return f"Error: could not launch any of {candidates}"

    for cmd in candidates:
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(0.1)
            if proc.returncode is None:
                return f"Opened {cmd}."
        except Exception:
            continue
    return f"Error: could not launch any of {candidates}"


async def _close_app(app_key: str, candidates: list[str]) -> str:
    """Close all processes matching the candidate names (Windows) or by name (Linux)."""
    if sys.platform == "win32":
        try:
            closed_any = False
            for cmd in candidates:
                exe = cmd.lower().replace(".exe", "")
                result = subprocess.run(
                    ["taskkill", "/IM", f"{exe}.exe", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    closed_any = True
            if closed_any:
                return f"Closed {app_key}."
            return f"Error: no running process found for {app_key}."
        except subprocess.TimeoutExpired:
            return f"Error: timeout closing {app_key}."
        except Exception as exc:
            return f"Error: could not close {app_key}: {exc}"

    try:
        closed_any = False
        for cmd in candidates:
            proc = await asyncio.create_subprocess_exec(
                "pkill",
                "-f",
                cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                closed_any = True
        if closed_any:
            return f"Closed {app_key}."
        return f"Error: no running process found for {app_key}."
    except Exception as exc:
        return f"Error: could not close {app_key}: {exc}"


def get_app_open_schema() -> dict:
    """Return the OpenAI function-calling schema for opening an app."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="app_open",
        description=(
            "Launch a predefined system application. "
            "Supported apps: notepad, terminal, calculator, browser, settings, explorer."
        ),
        parameters={
            "app": {
                "type": "string",
                "enum": list(_APPS.keys()),
                "description": "The predefined application to open.",
            },
        },
        required=["app"],
    )


def get_app_close_schema() -> dict:
    """Return the OpenAI function-calling schema for closing an app."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="app_close",
        description=(
            "Close a predefined system application. "
            "Supported apps: notepad, terminal, calculator, browser, settings, explorer. "
            "Closing an app requires user confirmation."
        ),
        parameters={
            "app": {
                "type": "string",
                "enum": list(_APPS.keys()),
                "description": "The predefined application to close.",
            },
        },
        required=["app"],
    )
