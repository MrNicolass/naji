"""Offline tests for the desktop notification tool."""

from __future__ import annotations

import asyncio

import pytest

import naji.core.tools.notification as notification
from naji.core.tools.notification import get_notify_schema, notify


@pytest.fixture(autouse=True)
def _reset_notifier():
    notification.set_notifier(None)
    yield
    notification.set_notifier(None)


def test_notify_schema() -> None:
    schema = get_notify_schema()

    assert schema["name"] == "notify"
    assert schema["parameters"]["required"] == ["message"]
    assert schema["parameters"]["properties"]["kind"]["enum"] == [
        "info",
        "success",
        "warning",
        "error",
    ]


async def test_notify_shows_via_registered_notifier() -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    result = await notify("Título", "Corpo", "warning")

    assert result == "Notification shown: Título."
    assert calls == [("Título", "Corpo", "warning")]


async def test_notify_defaults_title_to_app_name() -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    await notify("", "Corpo")

    assert calls[0][0] == "Naji"


async def test_notify_requires_a_message() -> None:
    notification.set_notifier(lambda *args: None)

    result = await notify("Título", "   ")

    assert result.startswith("Error:")


async def test_notify_invalid_kind_defaults_to_info() -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    await notify("Título", "Corpo", "bogus")  # type: ignore[arg-type]

    assert calls[0][2] == "info"


async def test_notify_falls_back_when_notifier_raises(monkeypatch) -> None:
    def broken(*_args: object) -> None:
        raise RuntimeError("boom")

    notification.set_notifier(broken)

    async def fake_platform(title: str, message: str, kind: str) -> str:
        return "Notification shown: platform."

    monkeypatch.setattr(notification, "_platform_notify", fake_platform)

    result = await notify("Título", "Corpo", "info")

    assert result == "Notification shown: platform."


async def test_notify_uses_platform_when_no_notifier(monkeypatch) -> None:
    async def fake_platform(title: str, message: str, kind: str) -> str:
        return "Notification shown: platform."

    monkeypatch.setattr(notification, "_platform_notify", fake_platform)

    result = await notify("Título", "Corpo", "info")

    assert result == "Notification shown: platform."


async def test_windows_command_passes_args_separately(monkeypatch) -> None:
    monkeypatch.setattr(notification.sys, "platform", "win32")
    captured: dict[str, list[str]] = {}

    async def fake_run_command(argv: list[str]) -> None:
        captured["argv"] = argv
        return None

    monkeypatch.setattr(notification, "_run_command", fake_run_command)

    result = await notification._platform_notify("Título", "Corpo", "warning")

    assert result == "Notification shown: Título."
    argv = captured["argv"]
    assert argv[0].endswith("powershell.exe")
    assert "Título" in argv
    assert "Corpo" in argv
    assert "warning" in argv


async def test_linux_command_uses_notify_send(monkeypatch) -> None:
    monkeypatch.setattr(notification.sys, "platform", "linux")
    captured: dict[str, list[str]] = {}

    async def fake_run_command(argv: list[str]) -> None:
        captured["argv"] = argv
        return None

    monkeypatch.setattr(notification, "_run_command", fake_run_command)

    result = await notification._platform_notify("Título", "Corpo", "error")

    assert result == "Notification shown: Título."
    argv = captured["argv"]
    assert argv[0] == "notify-send"
    assert "--icon=dialog-error" in argv
    assert "Título" in argv
    assert "Corpo" in argv


async def test_no_channel_platform_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(notification.sys, "platform", "darwin")

    result = await notification._platform_notify("Título", "Corpo", "info")

    assert result.startswith("Error:")


class _FakeProcess:
    def __init__(self, returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.returncode


async def test_run_command_success(monkeypatch) -> None:
    async def fake_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return _FakeProcess(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    assert await notification._run_command(["notify-send", "t", "m"]) is None


async def test_run_command_failure_includes_detail(monkeypatch) -> None:
    async def fake_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        return _FakeProcess(1, stderr=b"boom")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await notification._run_command(["notify-send", "t", "m"])

    assert result is not None
    assert "boom" in result


async def test_run_command_missing_binary(monkeypatch) -> None:
    async def fake_exec(*_args: object, **_kwargs: object) -> _FakeProcess:
        raise FileNotFoundError("nope")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await notification._run_command(["notify-send", "t", "m"])

    assert result is not None
    assert "not available" in result


async def test_run_command_timeout(monkeypatch) -> None:
    monkeypatch.setattr(notification, "_COMMAND_TIMEOUT_S", 0.05)

    class _HangingProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(5)
            return b"", b""

        def kill(self) -> None:
            pass

        async def wait(self) -> int:
            return 0

    async def fake_exec(*_args: object, **_kwargs: object) -> _HangingProcess:
        return _HangingProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await notification._run_command(["notify-send", "t", "m"])

    assert result is not None
    assert "timed out" in result
