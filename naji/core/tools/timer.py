"""Timer and reminder tools for the model tool registry.

Schedules desktop notifications that fire after a delay, reusing the
notification channel (tray balloon when the shell is running, platform
fallback otherwise). Timers live in memory and do not survive a restart.

All three tools are safe: they only schedule, list or cancel notifications
and never change system state, so none of them requires confirmation.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from naji.core.tools.notification import notify

log = logging.getLogger(__name__)

_MIN_SECONDS = 1
_MAX_SECONDS = 24 * 60 * 60
_MAX_ACTIVE = 20

_sleep = asyncio.sleep


@dataclass
class _PendingTimer:
    timer_id: str
    message: str
    seconds: float
    fires_at: datetime
    task: asyncio.Task[None]


class TimerService:
    """In-memory registry of pending timers."""

    def __init__(self) -> None:
        self._timers: dict[str, _PendingTimer] = {}
        self._counter = itertools.count(1)

    @property
    def active(self) -> list[_PendingTimer]:
        return sorted(self._timers.values(), key=lambda item: item.fires_at)

    def schedule(self, seconds: float, message: str) -> _PendingTimer:
        timer_id = f"t{next(self._counter)}"
        timer = _PendingTimer(
            timer_id=timer_id,
            message=message,
            seconds=seconds,
            fires_at=datetime.now() + timedelta(seconds=seconds),
            task=asyncio.create_task(self._fire(timer_id, seconds, message)),
        )
        self._timers[timer_id] = timer
        return timer

    def cancel(self, timer_id: str) -> _PendingTimer | None:
        timer = self._timers.pop(timer_id, None)
        if timer is not None:
            timer.task.cancel()
        return timer

    def clear(self) -> None:
        for timer in self._timers.values():
            timer.task.cancel()
        self._timers.clear()

    async def _fire(self, timer_id: str, seconds: float, message: str) -> None:
        try:
            await _sleep(seconds)
        except asyncio.CancelledError:
            self._timers.pop(timer_id, None)
            raise
        self._timers.pop(timer_id, None)
        try:
            await notify("", message, "info")
        except Exception:
            log.exception("Timer %s notification failed", timer_id)


_service = TimerService()


def get_service() -> TimerService:
    """Return the process-wide timer service."""
    return _service


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


async def set_timer(seconds: int, message: str = "") -> str:
    """Start a countdown timer that ends with a desktop notification."""
    text = (message or "").strip()
    if not text:
        return "Error: set_timer needs a short message for the reminder notification."
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return "Error: seconds must be an integer."
    if value < _MIN_SECONDS or value > _MAX_SECONDS:
        return f"Error: seconds must be between {_MIN_SECONDS} and {_MAX_SECONDS}."
    if len(_service.active) >= _MAX_ACTIVE:
        return f"Error: too many active timers (limit {_MAX_ACTIVE}). Cancel one first."
    timer = _service.schedule(value, text)
    return (
        f"Timer {timer.timer_id} set for {_format_duration(value)}. "
        f"It will notify at {timer.fires_at.strftime('%H:%M:%S')}."
    )


async def list_timers() -> str:
    """List the active timers with their ids, remaining time and messages."""
    active = _service.active
    if not active:
        return "There are no active timers."
    now = datetime.now()
    lines = [
        f"{item.timer_id}: {_format_duration((item.fires_at - now).total_seconds())} left — {item.message}"
        for item in active
    ]
    return "Active timers:\n" + "\n".join(lines)


async def cancel_timer(timer_id: str = "") -> str:
    """Cancel a pending timer by id, or the only active timer if id is omitted."""
    tid = (timer_id or "").strip()
    active = _service.active
    if not tid:
        if not active:
            return "There are no active timers to cancel."
        if len(active) > 1:
            ids = ", ".join(item.timer_id for item in active)
            return f"Error: multiple timers are active ({ids}). Specify timer_id."
        tid = active[0].timer_id
    timer = _service.cancel(tid)
    if timer is None:
        return f"Error: no active timer with id '{tid}'."
    return f"Timer {tid} cancelled."


def get_set_timer_schema() -> dict:
    """Return the OpenAI function-calling schema for set_timer."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="set_timer",
        description=(
            "Start a countdown timer or reminder. When it ends, Naji shows a "
            "desktop notification with the given message. Use it for requests "
            "like 'set a 10 minute timer' or 'remind me to stretch in an hour'."
        ),
        parameters={
            "seconds": {
                "type": "integer",
                "description": "How long to wait, in seconds (1 to 86400).",
            },
            "message": {
                "type": "string",
                "description": (
                    "Short reminder text shown in the notification when the "
                    "timer ends, written in the user's language."
                ),
            },
        },
        required=["seconds", "message"],
    )


def get_list_timers_schema() -> dict:
    """Return the OpenAI function-calling schema for list_timers."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="list_timers",
        description=(
            "List the active timers with their ids, remaining time and messages."
        ),
        parameters={},
        required=[],
    )


def get_cancel_timer_schema() -> dict:
    """Return the OpenAI function-calling schema for cancel_timer."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="cancel_timer",
        description=(
            "Cancel a pending timer before it ends. Omit timer_id when only "
            "one timer is active; otherwise pass the id shown by list_timers."
        ),
        parameters={
            "timer_id": {
                "type": "string",
                "description": "Id of the timer to cancel (e.g. 't1'). Optional.",
            },
        },
        required=[],
    )
