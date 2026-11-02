"""Power controls for the model tool registry.

Every power action interrupts the user's session, so all four tools are
registered as dangerous and require explicit confirmation in the bar before
they run. On Windows, shutdown and restart use a short delay so the spoken
answer can finish before the machine powers off.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

WINDOWS_SHUTDOWN_DELAY_S = 10


async def lock_screen() -> str:
    """Lock the workstation. Requires user confirmation."""
    if sys.platform == "win32":
        return await _run_windows(
            ["rundll32.exe", "user32.dll,LockWorkStation"],
            "Screen locked.",
        )
    return await _run_linux(
        [
            ["loginctl", "lock-session"],
            ["xdg-screensaver", "lock"],
            ["gnome-screensaver-command", "--lock"],
        ],
        "Screen locked.",
    )


async def sleep_pc() -> str:
    """Put the computer to sleep. Requires user confirmation."""
    if sys.platform == "win32":
        return await _run_windows(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "The computer is going to sleep.",
        )
    return await _run_linux(
        [
            ["systemctl", "suspend"],
            ["loginctl", "suspend"],
        ],
        "The computer is going to sleep.",
    )


async def shutdown_pc() -> str:
    """Shut down the computer. Requires user confirmation."""
    if sys.platform == "win32":
        return await _run_windows(
            ["shutdown", "/s", "/t", str(WINDOWS_SHUTDOWN_DELAY_S)],
            f"The computer will shut down in {WINDOWS_SHUTDOWN_DELAY_S} seconds.",
        )
    return await _run_linux(
        [
            ["loginctl", "poweroff"],
            ["systemctl", "poweroff"],
            ["shutdown", "-h", "now"],
        ],
        "The computer is shutting down.",
    )


async def restart_pc() -> str:
    """Restart the computer. Requires user confirmation."""
    if sys.platform == "win32":
        return await _run_windows(
            ["shutdown", "/r", "/t", str(WINDOWS_SHUTDOWN_DELAY_S)],
            f"The computer will restart in {WINDOWS_SHUTDOWN_DELAY_S} seconds.",
        )
    return await _run_linux(
        [
            ["loginctl", "reboot"],
            ["systemctl", "reboot"],
            ["shutdown", "-r", "now"],
        ],
        "The computer is restarting.",
    )


async def _run_windows(cmd: list[str], ok: str) -> str:
    """Start a fire-and-forget Windows command."""
    try:
        subprocess.Popen(cmd)
        return ok
    except Exception as exc:
        return f"Error: could not start {cmd[0]}: {exc}"


async def _run_linux(candidates: list[list[str]], ok: str) -> str:
    """Run the first candidate that exits successfully."""
    for cmd in candidates:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                return ok
        except Exception:
            continue
    return f"Error: none of {[c[0] for c in candidates]} could be executed"


def get_lock_screen_schema() -> dict:
    """Return the OpenAI function-calling schema for locking the screen."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="lock_screen",
        description=(
            "Lock the user's screen. Use it when the user asks to lock the "
            "screen or lock the computer. Requires user confirmation."
        ),
        parameters={},
    )


def get_sleep_pc_schema() -> dict:
    """Return the OpenAI function-calling schema for sleeping the computer."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="sleep_pc",
        description=(
            "Put the computer to sleep. Use it when the user asks to sleep, "
            "suspend or rest the computer. Requires user confirmation."
        ),
        parameters={},
    )


def get_shutdown_pc_schema() -> dict:
    """Return the OpenAI function-calling schema for shutting down."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="shutdown_pc",
        description=(
            "Shut down the computer. Use it when the user asks to shut down, "
            "power off or turn off the computer. Requires user confirmation."
        ),
        parameters={},
    )


def get_restart_pc_schema() -> dict:
    """Return the OpenAI function-calling schema for restarting."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="restart_pc",
        description=(
            "Restart the computer. Use it when the user asks to restart or "
            "reboot the computer. Requires user confirmation."
        ),
        parameters={},
    )
