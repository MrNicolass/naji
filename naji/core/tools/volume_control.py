"""System volume controls for the model tool registry."""

from __future__ import annotations

import asyncio
import sys
from typing import Literal

VolumeAction = Literal["toggle_mute", "up", "down"]


async def volume_control(action: VolumeAction) -> str:
    """Change the system output volume without relying on the focused app."""
    if action not in {"toggle_mute", "up", "down"}:
        return f"Error: unsupported volume action: {action}"

    if sys.platform == "win32":
        from naji.platform.windows import volume_down, volume_mute, volume_up

        commands = {
            "toggle_mute": volume_mute,
            "up": volume_up,
            "down": volume_down,
        }
        commands[action]()
        return f"System volume action completed: {action}."

    return await _volume_control_linux(action)


async def _volume_control_linux(action: VolumeAction) -> str:
    """Use PulseAudio/PipeWire's pactl command on supported Linux desktops."""
    action_args = {
        "toggle_mute": ("set-sink-mute", "@DEFAULT_SINK@", "toggle"),
        "up": ("set-sink-volume", "@DEFAULT_SINK@", "+5%"),
        "down": ("set-sink-volume", "@DEFAULT_SINK@", "-5%"),
    }
    try:
        process = await asyncio.create_subprocess_exec(
            "pactl",
            *action_args[action],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
    except FileNotFoundError:
        return "Error: pactl is not installed, so system volume cannot be changed."
    except OSError as exc:
        return f"Error: could not run pactl: {exc}"

    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()
        return f"Error: pactl failed to change system volume: {detail or process.returncode}"
    return f"System volume action completed: {action}."


def get_volume_control_schema() -> dict:
    """Return the OpenAI function-calling schema for system volume control."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="volume_control",
        description="Controls the system output volume or toggles system mute.",
        parameters={
            "action": {
                "type": "string",
                "enum": ["toggle_mute", "up", "down"],
                "description": "The volume action to perform.",
            }
        },
        required=["action"],
    )
