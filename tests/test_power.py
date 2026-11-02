"""Offline tests for the power control tools."""

from __future__ import annotations

import subprocess

import naji.core.tools.power as power_tool
from naji.core.tools.power import (
    get_lock_screen_schema,
    get_restart_pc_schema,
    get_shutdown_pc_schema,
    get_sleep_pc_schema,
    lock_screen,
    restart_pc,
    shutdown_pc,
    sleep_pc,
)


def test_power_schemas() -> None:
    schemas = {
        "lock_screen": get_lock_screen_schema(),
        "sleep_pc": get_sleep_pc_schema(),
        "shutdown_pc": get_shutdown_pc_schema(),
        "restart_pc": get_restart_pc_schema(),
    }
    for name, schema in schemas.items():
        assert schema["name"] == name
        assert schema["parameters"]["properties"] == {}
        assert schema["parameters"]["required"] == []
        assert "confirmation" in schema["description"].lower()


def _fake_popen(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            calls.append(cmd)

    monkeypatch.setattr(power_tool.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return calls


async def test_lock_screen_windows(monkeypatch) -> None:
    calls = _fake_popen(monkeypatch)

    result = await lock_screen()

    assert result == "Screen locked."
    assert calls == [["rundll32.exe", "user32.dll,LockWorkStation"]]


async def test_sleep_pc_windows(monkeypatch) -> None:
    calls = _fake_popen(monkeypatch)

    result = await sleep_pc()

    assert result == "The computer is going to sleep."
    assert calls == [["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]]


async def test_shutdown_pc_windows(monkeypatch) -> None:
    calls = _fake_popen(monkeypatch)

    result = await shutdown_pc()

    assert "10 seconds" in result
    assert calls == [["shutdown", "/s", "/t", "10"]]


async def test_restart_pc_windows(monkeypatch) -> None:
    calls = _fake_popen(monkeypatch)

    result = await restart_pc()

    assert "10 seconds" in result
    assert calls == [["shutdown", "/r", "/t", "10"]]


async def test_linux_uses_first_working_candidate(monkeypatch) -> None:
    created: list[list[str]] = []

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        created.append(list(cmd))
        return FakeProc()

    monkeypatch.setattr(power_tool.sys, "platform", "linux")
    monkeypatch.setattr(power_tool.asyncio, "create_subprocess_exec", fake_exec)

    result = await shutdown_pc()

    assert result == "The computer is shutting down."
    assert created == [["loginctl", "poweroff"]]


async def test_linux_reports_error_when_no_candidate_works(monkeypatch) -> None:
    class FakeProc:
        returncode = 1

        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*cmd, **kwargs):
        return FakeProc()

    monkeypatch.setattr(power_tool.sys, "platform", "linux")
    monkeypatch.setattr(power_tool.asyncio, "create_subprocess_exec", fake_exec)

    result = await lock_screen()

    assert result.startswith("Error:")
