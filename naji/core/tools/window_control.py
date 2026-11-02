"""Window controls for the model tool registry.

Focusing and minimizing a window are safe actions. Closing a window is
destructive (unsaved work may be lost) and is registered as a dangerous tool
that requires explicit confirmation in the bar before it runs.

Windows uses the Win32 API through ctypes; Linux uses wmctrl.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import Any

WM_CLOSE = 0x0010
SW_RESTORE = 9
SW_MINIMIZE = 6
ASFW_ANY = 0xFFFFFFFF


def _linux_requirement_error() -> str | None:
    """Return an actionable error when the Linux window manager tool is missing."""
    if sys.platform == "win32" or shutil.which("wmctrl") is not None:
        return None
    return "Error: window control requires wmctrl to be installed on Linux."


async def window_focus(title: str) -> str:
    """Bring the window whose title matches to the front."""
    error = _linux_requirement_error()
    if error:
        return error
    found = await _find_window(title)
    if found is None:
        return f"Error: no window matching '{title}' found."
    handle, actual = found
    if await _focus(handle):
        return f"Focused window {actual}."
    return f"Error: could not bring window {actual} to the front."


async def window_minimize(title: str) -> str:
    """Minimize the window whose title matches."""
    error = _linux_requirement_error()
    if error:
        return error
    found = await _find_window(title)
    if found is None:
        return f"Error: no window matching '{title}' found."
    handle, actual = found
    if await _minimize(handle):
        return f"Minimized window {actual}."
    return f"Error: could not minimize window {actual}."


async def window_close(title: str) -> str:
    """Close the window whose title matches. Requires user confirmation."""
    error = _linux_requirement_error()
    if error:
        return error
    found = await _find_window(title)
    if found is None:
        return f"Error: no window matching '{title}' found."
    handle, actual = found
    if await _close(handle):
        return f"Closed window {actual}."
    return f"Error: could not close window {actual}."


async def _find_window(title: str) -> tuple[Any, str] | None:
    """Match a visible top-level window by exact or partial title."""
    windows = await _list_windows()
    query = (title or "").strip().casefold()
    if not query:
        return None
    for window in windows:
        if window[1].casefold() == query:
            return window
    partial = [window for window in windows if query in window[1].casefold()]
    if partial:
        partial.sort(key=lambda window: len(window[1]))
        return partial[0]
    return None


async def _list_windows() -> list[tuple[Any, str]]:
    """List visible top-level windows as (handle, title) pairs."""
    if sys.platform == "win32":
        return _list_windows_win()
    return await _list_windows_linux()


def _list_windows_win() -> list[tuple[int, str]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    wndenumproc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.EnumWindows.argtypes = [wndenumproc, wintypes.LPARAM]

    found: list[tuple[int, str]] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                found.append((hwnd, buffer.value))
        return True

    user32.EnumWindows(wndenumproc(_callback), 0)
    return found


async def _list_windows_linux() -> list[tuple[str, str]]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "wmctrl",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception:
        return []
    windows: list[tuple[str, str]] = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        parts = line.split(None, 5)
        if len(parts) >= 6 and parts[5].strip():
            windows.append((parts[0], parts[5].strip()))
    return windows


async def _focus(handle: Any) -> bool:
    if sys.platform == "win32":
        return _focus_win(handle)
    return await _run_wmctrl(["-ia", str(handle)])


def _focus_win(handle: int) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.AllowSetForegroundWindow.argtypes = [ctypes.c_uint]
    if user32.IsIconic(handle):
        user32.ShowWindow(handle, SW_RESTORE)
    if user32.SetForegroundWindow(handle):
        return True
    user32.AllowSetForegroundWindow(ASFW_ANY)
    return bool(user32.SetForegroundWindow(handle))


async def _minimize(handle: Any) -> bool:
    if sys.platform == "win32":
        return _minimize_win(handle)
    return await _run_wmctrl(["-ir", str(handle), "-b", "add,hidden,1"])


def _minimize_win(handle: int) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    return bool(user32.ShowWindow(handle, SW_MINIMIZE))


async def _close(handle: Any) -> bool:
    if sys.platform == "win32":
        return _close_win(handle)
    return await _run_wmctrl(["-ic", str(handle)])


def _close_win(handle: int) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        ctypes.c_uint,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    return bool(user32.PostMessageW(handle, WM_CLOSE, 0, 0))


async def _run_wmctrl(args: list[str]) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "wmctrl",
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except Exception:
        return False


def get_window_focus_schema() -> dict:
    """Return the OpenAI function-calling schema for focusing a window."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="window_focus",
        description=(
            "Bring an already open window to the front. Match it by part of "
            "its title, e.g. 'Code' or 'Outlook'. Use it when the user asks "
            "to show, focus or switch to a window."
        ),
        parameters={
            "title": {
                "type": "string",
                "description": "Part of the window title to match.",
            },
        },
        required=["title"],
    )


def get_window_minimize_schema() -> dict:
    """Return the OpenAI function-calling schema for minimizing a window."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="window_minimize",
        description=(
            "Minimize an already open window. Match it by part of its title, "
            "e.g. 'Code' or 'Outlook'. Use it when the user asks to minimize "
            "or hide a window."
        ),
        parameters={
            "title": {
                "type": "string",
                "description": "Part of the window title to match.",
            },
        },
        required=["title"],
    )


def get_window_close_schema() -> dict:
    """Return the OpenAI function-calling schema for closing a window."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="window_close",
        description=(
            "Close an already open window. Match it by part of its title, "
            "e.g. 'Code' or 'Outlook'. The window is asked to close politely, "
            "so it may ask to save unsaved work. Closing a window requires "
            "user confirmation."
        ),
        parameters={
            "title": {
                "type": "string",
                "description": "Part of the window title to match.",
            },
        },
        required=["title"],
    )
