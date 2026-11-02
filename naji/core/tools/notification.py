"""Desktop notification tool for the model tool registry.

Shows a system notification. When the desktop shell is running, the tray icon is
registered as the notifier (see :func:`set_notifier`) so the balloon reuses the
same icon. Otherwise the tool falls back to a platform notification (PowerShell
on Windows, ``notify-send`` on Linux) so it still works headless or in tests.

The tool is safe: it only displays a message and never changes system state.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable

log = logging.getLogger(__name__)

# Signature: (title, message, kind) -> None
Notifier = Callable[[str, str, str], None]

_notifier: Notifier | None = None

_KINDS = ("info", "success", "warning", "error")
_DEFAULT_TITLE = "Naji"
_COMMAND_TIMEOUT_S = 10.0


def set_notifier(notifier: Notifier | None) -> None:
    """Register the callback used to display notifications (e.g. the tray)."""
    global _notifier
    _notifier = notifier


def get_notifier() -> Notifier | None:
    """Return the registered notifier, if any."""
    return _notifier


async def notify(title: str, message: str, kind: str = "info") -> str:
    """Show a desktop notification and return a confirmation for the model."""
    title = (title or "").strip() or _DEFAULT_TITLE
    message = (message or "").strip()
    if not message:
        return "Error: a notification needs a non-empty message."
    if kind not in _KINDS:
        kind = "info"

    if _notifier is not None:
        try:
            _notifier(title, message, kind)
        except Exception:
            log.exception("Notifier callback failed; using platform fallback")
            return await _platform_notify(title, message, kind)
        return f"Notification shown: {title}."

    return await _platform_notify(title, message, kind)


async def _platform_notify(title: str, message: str, kind: str) -> str:
    """Best-effort notification without the desktop shell (tests/headless)."""
    if sys.platform == "win32":
        error = await _notify_windows(title, message, kind)
    elif sys.platform.startswith("linux"):
        error = await _notify_linux(title, message, kind)
    else:
        return "Error: no notification channel is available on this platform."
    if error is None:
        return f"Notification shown: {title}."
    return error


async def _notify_windows(title: str, message: str, kind: str) -> str | None:
    """Show a balloon via a PowerShell NotifyIcon. Title/message/kind are passed
    as separate process arguments so they are never interpolated into the script."""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$icon = switch ($args[2]) { "
        '"warning" { [System.Drawing.SystemIcons]::Warning } '
        '"error" { [System.Drawing.SystemIcons]::Error } '
        "default { [System.Drawing.SystemIcons]::Information } }; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = $icon; "
        "$n.BalloonTipTitle = $args[0]; "
        "$n.BalloonTipText = $args[1]; "
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(4000); "
        "Start-Sleep -Seconds 4; "
        "$n.Dispose()"
    )
    return await _run_command(
        ["powershell.exe", "-NoProfile", "-Command", script, title, message, kind]
    )


async def _notify_linux(title: str, message: str, kind: str) -> str | None:
    """Show a notification via notify-send (libnotify), used by most Linux DEs."""
    icon = {
        "info": "dialog-information",
        "success": "dialog-information",
        "warning": "dialog-warning",
        "error": "dialog-error",
    }[kind]
    return await _run_command(["notify-send", f"--icon={icon}", title, message])


async def _run_command(argv: list[str]) -> str | None:
    """Run a notification command. Returns None on success, an error on failure."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return "Error: the platform notification command is not available."
    except OSError as exc:
        return f"Error: could not run the notification command: {exc}"

    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=_COMMAND_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        return "Error: the notification command timed out."

    if process.returncode != 0:
        detail = (stderr or b"").decode(errors="replace").strip()
        return f"Error: the notification failed: {detail or process.returncode}"
    return None


def get_notify_schema() -> dict:
    """Return the OpenAI function-calling schema for the notification tool."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="notify",
        description=(
            "Show a desktop notification (a system tray balloon) with a short "
            "title and a message. Use it to inform the user without opening the "
            "bar, for reminders or status updates."
        ),
        parameters={
            "title": {
                "type": "string",
                "description": "Short notification title. Optional; defaults to 'Naji'.",
            },
            "message": {
                "type": "string",
                "description": "The notification body shown to the user.",
            },
            "kind": {
                "type": "string",
                "enum": list(_KINDS),
                "description": "Notification style. Optional; defaults to 'info'.",
            },
        },
        required=["message"],
    )
