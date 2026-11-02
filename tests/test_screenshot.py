"""Offline tests for the screenshot tool."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import naji.core.tools.screenshot as screenshot_tool
from naji.core.tools.screenshot import get_screenshot_schema, take_screenshot


def test_screenshot_schema() -> None:
    schema = get_screenshot_schema()

    assert schema["name"] == "take_screenshot"
    assert schema["parameters"]["properties"] == {}
    assert schema["parameters"]["required"] == []


async def test_take_screenshot_saves_png(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(screenshot_tool, "get_screenshot_dir", lambda: tmp_path)

    result = await take_screenshot()

    assert result.startswith(str(tmp_path))
    assert result.endswith(".png")
    target = Path(result)
    assert target.exists()
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


async def test_take_screenshot_unique_names(qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(screenshot_tool, "get_screenshot_dir", lambda: tmp_path)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return cls(2026, 11, 2, 12, 0, 0)

    monkeypatch.setattr(screenshot_tool, "datetime", FixedDatetime)

    first = await take_screenshot()
    second = await take_screenshot()

    assert first != second
    assert Path(first).exists()
    assert Path(second).exists()
