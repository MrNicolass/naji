"""Offline tests for the app open/close tools."""

from __future__ import annotations

import subprocess

import naji.core.tools.app_control as app_tool
from naji.core.tools.app_control import (
    app_close,
    app_open,
    get_app_close_schema,
    get_app_open_schema,
)


def test_app_open_schema() -> None:
    schema = get_app_open_schema()

    assert schema["name"] == "app_open"
    assert schema["parameters"]["required"] == ["app"]
    assert schema["parameters"]["properties"]["app"]["enum"] == list(
        app_tool._APPS.keys()
    )


def test_app_close_schema() -> None:
    schema = get_app_close_schema()

    assert schema["name"] == "app_close"
    assert schema["parameters"]["required"] == ["app"]
    assert "confirmation" in schema["description"].lower()


async def test_app_open_rejects_unknown_app() -> None:
    result = await app_open("unknown_app")

    assert result == "Error: unknown application 'unknown_app'"


async def test_app_close_rejects_unknown_app() -> None:
    result = await app_close("unknown_app")

    assert result == "Error: unknown application 'unknown_app'"


async def test_app_open_dispatches_open_windows(monkeypatch) -> None:
    calls: list[list[str]] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            calls.append(cmd)
            self.returncode = None

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(app_tool.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "Popen", FakePopen)

    result = await app_open("notepad")
    assert "Opened" in result
    assert calls


async def test_app_close_dispatches_close_windows(monkeypatch) -> None:
    results: list[subprocess.CompletedProcess] = []

    def fake_run(*args, **kwargs):
        cp = subprocess.CompletedProcess(args[0], 0, "", "")
        results.append(cp)
        return cp

    monkeypatch.setattr(app_tool.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await app_close("notepad")
    assert "Closed" in result or "Error" in result
    assert results
