"""Offline tests for the system volume tool."""

from __future__ import annotations

import naji.core.tools.volume_control as volume_tool
from naji.core.tools.volume_control import get_volume_control_schema, volume_control


def test_volume_control_schema() -> None:
    schema = get_volume_control_schema()

    assert schema["name"] == "volume_control"
    assert schema["parameters"]["required"] == ["action"]
    assert schema["parameters"]["properties"]["action"]["enum"] == [
        "toggle_mute",
        "up",
        "down",
    ]


async def test_volume_control_rejects_unknown_action() -> None:
    result = await volume_control("invalid")  # type: ignore[arg-type]

    assert result == "Error: unsupported volume action: invalid"


async def test_volume_control_dispatches_windows_actions(monkeypatch) -> None:
    from naji.platform import windows

    calls: list[str] = []
    monkeypatch.setattr(volume_tool.sys, "platform", "win32")
    monkeypatch.setattr(windows, "volume_mute", lambda: calls.append("toggle_mute"))
    monkeypatch.setattr(windows, "volume_up", lambda: calls.append("up"))
    monkeypatch.setattr(windows, "volume_down", lambda: calls.append("down"))

    for action in ("toggle_mute", "up", "down"):
        assert await volume_control(action) == f"System volume action completed: {action}."

    assert calls == ["toggle_mute", "up", "down"]
