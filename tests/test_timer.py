"""Offline tests for the timer and reminder tools."""

from __future__ import annotations

import asyncio

import pytest

import naji.core.tools.notification as notification
import naji.core.tools.timer as timer
from naji.core.tools.timer import (
    TimerService,
    _format_duration,
    cancel_timer,
    get_cancel_timer_schema,
    get_list_timers_schema,
    get_set_timer_schema,
    list_timers,
    set_timer,
)


@pytest.fixture(autouse=True)
async def _fresh_service(monkeypatch):
    service = TimerService()
    monkeypatch.setattr(timer, "_service", service)
    notification.set_notifier(None)
    yield service
    tasks = [item.task for item in service.active]
    service.clear()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    notification.set_notifier(None)


def test_set_timer_schema() -> None:
    schema = get_set_timer_schema()

    assert schema["name"] == "set_timer"
    assert schema["parameters"]["required"] == ["seconds", "message"]
    assert schema["parameters"]["properties"]["seconds"]["type"] == "integer"


def test_list_timers_schema() -> None:
    schema = get_list_timers_schema()

    assert schema["name"] == "list_timers"
    assert schema["parameters"]["properties"] == {}
    assert schema["parameters"]["required"] == []


def test_cancel_timer_schema() -> None:
    schema = get_cancel_timer_schema()

    assert schema["name"] == "cancel_timer"
    assert "timer_id" in schema["parameters"]["properties"]
    assert schema["parameters"]["required"] == []


def test_format_duration() -> None:
    assert _format_duration(45) == "45s"
    assert _format_duration(90) == "1m 30s"
    assert _format_duration(3661) == "1h 01m"
    assert _format_duration(-5) == "0s"


async def test_set_timer_returns_id_and_duration() -> None:
    result = await set_timer(90, "beber água")

    assert "t1" in result
    assert "1m 30s" in result
    assert [item.timer_id for item in timer._service.active] == ["t1"]


async def test_set_timer_requires_a_message() -> None:
    result = await set_timer(60, "   ")

    assert result.startswith("Error:")
    assert timer._service.active == []


@pytest.mark.parametrize("seconds", [0, -10, 86401, "abc", None])
async def test_set_timer_rejects_bad_seconds(seconds: object) -> None:
    result = await set_timer(seconds, "mensagem")  # type: ignore[arg-type]

    assert result.startswith("Error:")
    assert timer._service.active == []


async def test_set_timer_enforces_max_active(monkeypatch) -> None:
    monkeypatch.setattr(timer, "_MAX_ACTIVE", 2)

    await set_timer(60, "um")
    await set_timer(60, "dois")
    result = await set_timer(60, "três")

    assert result.startswith("Error:")
    assert len(timer._service.active) == 2


async def test_list_timers_empty() -> None:
    result = await list_timers()

    assert "no active timers" in result


async def test_list_timers_shows_ids_and_messages() -> None:
    await set_timer(120, "beber água")
    await set_timer(600, "reunião")

    result = await list_timers()

    assert "t1" in result
    assert "t2" in result
    assert "beber água" in result
    assert "reunião" in result


async def test_cancel_timer_by_id() -> None:
    await set_timer(60, "mensagem")

    result = await cancel_timer("t1")

    assert "t1" in result
    assert "cancelled" in result
    assert timer._service.active == []


async def test_cancel_timer_without_id_cancels_the_only_one() -> None:
    await set_timer(60, "mensagem")

    result = await cancel_timer()

    assert "cancelled" in result
    assert timer._service.active == []


async def test_cancel_timer_without_id_requires_id_when_multiple() -> None:
    await set_timer(60, "um")
    await set_timer(120, "dois")

    result = await cancel_timer()

    assert result.startswith("Error:")
    assert "t1" in result
    assert "t2" in result
    assert len(timer._service.active) == 2


async def test_cancel_unknown_timer_id() -> None:
    result = await cancel_timer("t9")

    assert result.startswith("Error:")


async def test_cancel_with_no_timers() -> None:
    result = await cancel_timer()

    assert "no active timers" in result


async def test_fired_timer_sends_notification() -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    timer._service.schedule(0.05, "tempo esgotado")
    await asyncio.sleep(0.2)

    assert calls == [("Naji", "tempo esgotado", "info")]
    assert timer._service.active == []


async def test_cancelled_timer_does_not_notify() -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    pending = timer._service.schedule(0.5, "tempo esgotado")
    timer._service.cancel(pending.timer_id)
    await asyncio.sleep(0.7)

    assert calls == []


async def test_set_timer_fires_notification(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []
    notification.set_notifier(lambda t, m, k: calls.append((t, m, k)))

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(timer, "_sleep", instant)

    result = await set_timer(60, "lembrete")
    await asyncio.sleep(0.01)

    assert "t1" in result
    assert calls == [("Naji", "lembrete", "info")]
    assert timer._service.active == []
