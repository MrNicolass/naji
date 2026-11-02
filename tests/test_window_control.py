"""Offline tests for the window control tools."""

from __future__ import annotations

import naji.core.tools.window_control as window_tool
from naji.core.tools.window_control import (
    get_window_close_schema,
    get_window_focus_schema,
    get_window_minimize_schema,
    window_close,
    window_focus,
    window_minimize,
)


def test_window_schemas() -> None:
    schemas = {
        "window_focus": get_window_focus_schema(),
        "window_minimize": get_window_minimize_schema(),
        "window_close": get_window_close_schema(),
    }
    for name, schema in schemas.items():
        assert schema["name"] == name
        assert schema["parameters"]["required"] == ["title"]
    assert "confirmation" in get_window_close_schema()["description"].lower()
    assert "confirmation" not in get_window_focus_schema()["description"].lower()
    assert "confirmation" not in get_window_minimize_schema()["description"].lower()


def _patch_windows(monkeypatch, windows: list[tuple[object, str]]) -> None:
    async def fake_list() -> list[tuple[object, str]]:
        return windows

    monkeypatch.setattr(window_tool.sys, "platform", "win32")
    monkeypatch.setattr(window_tool, "_list_windows", fake_list)


async def test_focus_reports_no_match(monkeypatch) -> None:
    _patch_windows(monkeypatch, [])

    result = await window_focus("Notepad")

    assert result == "Error: no window matching 'Notepad' found."


async def test_minimize_reports_no_match(monkeypatch) -> None:
    _patch_windows(monkeypatch, [])

    result = await window_minimize("Notepad")

    assert result == "Error: no window matching 'Notepad' found."


async def test_close_reports_no_match(monkeypatch) -> None:
    _patch_windows(monkeypatch, [])

    result = await window_close("Notepad")

    assert result == "Error: no window matching 'Notepad' found."


async def test_find_prefers_exact_then_shortest_partial(monkeypatch) -> None:
    windows = [
        (1, "Visual Studio Code"),
        (2, "Code - settings"),
        (3, "Microsoft Edge"),
    ]
    _patch_windows(monkeypatch, windows)

    assert await window_tool._find_window("Visual Studio Code") == (
        1,
        "Visual Studio Code",
    )
    assert await window_tool._find_window("code") == (2, "Code - settings")
    assert await window_tool._find_window("firefox") is None
    assert await window_tool._find_window("   ") is None


async def test_focus_windows(monkeypatch) -> None:
    calls: list[int] = []

    def fake_focus_win(handle: int) -> bool:
        calls.append(handle)
        return True

    _patch_windows(monkeypatch, [(7, "Notepad")])
    monkeypatch.setattr(window_tool, "_focus_win", fake_focus_win)

    result = await window_focus("Notepad")

    assert result == "Focused window Notepad."
    assert calls == [7]


async def test_focus_windows_reports_failure(monkeypatch) -> None:
    _patch_windows(monkeypatch, [(7, "Notepad")])
    monkeypatch.setattr(window_tool, "_focus_win", lambda handle: False)

    result = await window_focus("Notepad")

    assert result == "Error: could not bring window Notepad to the front."


async def test_minimize_windows(monkeypatch) -> None:
    calls: list[int] = []

    def fake_minimize_win(handle: int) -> bool:
        calls.append(handle)
        return True

    _patch_windows(monkeypatch, [(9, "Calculator")])
    monkeypatch.setattr(window_tool, "_minimize_win", fake_minimize_win)

    result = await window_minimize("Calculator")

    assert result == "Minimized window Calculator."
    assert calls == [9]


async def test_close_windows(monkeypatch) -> None:
    calls: list[int] = []

    def fake_close_win(handle: int) -> bool:
        calls.append(handle)
        return True

    _patch_windows(monkeypatch, [(11, "Notepad")])
    monkeypatch.setattr(window_tool, "_close_win", fake_close_win)

    result = await window_close("Notepad")

    assert result == "Closed window Notepad."
    assert calls == [11]


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")


async def test_close_linux_uses_wmctrl(monkeypatch) -> None:
    created: list[list[str]] = []

    async def fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        created.append(list(cmd))
        return _FakeProc(0)

    async def fake_list() -> list[tuple[str, str]]:
        return [("0x0123", "Notepad")]

    monkeypatch.setattr(window_tool.sys, "platform", "linux")
    monkeypatch.setattr(window_tool, "_linux_requirement_error", lambda: None)
    monkeypatch.setattr(window_tool, "_list_windows", fake_list)
    monkeypatch.setattr(window_tool.asyncio, "create_subprocess_exec", fake_exec)

    result = await window_close("Notepad")

    assert result == "Closed window Notepad."
    assert created == [["wmctrl", "-ic", "0x0123"]]


async def test_focus_linux_uses_wmctrl(monkeypatch) -> None:
    created: list[list[str]] = []

    async def fake_exec(*cmd: str, **kwargs: object) -> _FakeProc:
        created.append(list(cmd))
        return _FakeProc(0)

    async def fake_list() -> list[tuple[str, str]]:
        return [("0x0456", "Terminal")]

    monkeypatch.setattr(window_tool.sys, "platform", "linux")
    monkeypatch.setattr(window_tool, "_linux_requirement_error", lambda: None)
    monkeypatch.setattr(window_tool, "_list_windows", fake_list)
    monkeypatch.setattr(window_tool.asyncio, "create_subprocess_exec", fake_exec)

    result = await window_focus("Terminal")

    assert result == "Focused window Terminal."
    assert created == [["wmctrl", "-ia", "0x0456"]]


async def test_linux_without_wmctrl_reports_error(monkeypatch) -> None:
    monkeypatch.setattr(window_tool.sys, "platform", "linux")
    monkeypatch.setattr(window_tool.shutil, "which", lambda name: None)

    result = await window_focus("Notepad")

    assert result.startswith("Error:")
    assert "wmctrl" in result
