"""Controller voice-flow tests (offscreen, no real audio or network)."""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path

import numpy as np
import pytest

from naji.config import Config
from naji.controller.app import AppController
from naji.core.tools import notification
from naji.i18n import Translator
from naji.ui.bar import NajiBar
from naji.ui.theme import get_tokens
from naji.ui.tray import NajiTray

CHUNK = 480  # 30 ms at 16 kHz


class FakeRecorder:
    """Replays scripted chunk sessions, like PushToTalkRecorder."""

    def __init__(self, sessions: list[list[np.ndarray]]) -> None:
        self._sessions = sessions
        self._index = 0
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._recorded: list[np.ndarray] = []
        self.start_count = 0

    def reset(self) -> None:
        self._queue = queue.Queue()
        self._recorded = []

    def start(self) -> None:
        self.start_count += 1
        self._recorded = []
        chunks = self._sessions[self._index] if self._index < len(self._sessions) else []
        for chunk in chunks:
            self._queue.put(chunk)

    def take_chunk(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            chunk = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        self._recorded.append(chunk)
        return chunk

    def stop(self) -> np.ndarray:
        while True:
            try:
                self._recorded.append(self._queue.get_nowait())
            except queue.Empty:
                break
        self._index += 1
        if not self._recorded:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(self._recorded)

    def cancel(self) -> None:
        self._queue = queue.Queue()
        self._recorded = []


def _silence() -> np.ndarray:
    return np.zeros(CHUNK, dtype=np.int16)


def _speech() -> np.ndarray:
    return np.full(CHUNK, 1500, dtype=np.int16)


def _vad_session() -> list[np.ndarray]:
    """300 ms of calibration silence, 600 ms of speech, then silence."""
    return [_silence()] * 10 + [_speech()] * 20 + [_silence()] * 30


@pytest.fixture
def controller(qapp, monkeypatch):
    config = Config()
    config.ui.reduced_motion = True
    config.ui.speech_mode = "vad"
    config.wake.enabled = False
    translator = Translator("pt-BR")
    tokens = get_tokens("dark")
    bar = NajiBar(config, translator, tokens)
    tray = NajiTray(config, translator, tokens)
    instance = AppController(qapp, config, Path("unused.yaml"), translator, bar, tray)

    monkeypatch.setattr(notification, "_notifier", None, raising=False)

    async def fake_request_tts(*args, **kwargs):
        return (b"", "audio/pcm;rate=24000")

    monkeypatch.setattr("naji.controller.app.request_tts", fake_request_tts)

    async def fake_transcribe(samples):
        return "olá"

    async def fake_reply(text, **kwargs):
        return "oi"

    monkeypatch.setattr(instance, "_transcribe", fake_transcribe)
    monkeypatch.setattr(instance._assistant, "reply", fake_reply)
    yield instance

    # The event loop is already closed here; turns must be cancelled inside
    # the test (see _finish) before widgets are torn down.
    bar.deleteLater()
    tray.deleteLater()
    qapp.processEvents()


async def _wait_until(predicate, timeout: float = 10.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


async def _finish(controller) -> None:
    controller._cancel_turn()
    await asyncio.sleep(0.1)


def test_bar_hidden_starts_new_conversation(controller) -> None:
    controller._assistant._history.append({"role": "user", "content": "olá"})
    controller._bar.show_bar("summoned")
    controller._bar.hide_bar()
    assert controller._assistant._history == []
    assert controller._bar._history == []


async def test_vad_turn_starts_follow_up_listening(controller) -> None:
    controller._config.ui.follow_up_ms = 60000
    recorder = FakeRecorder([_vad_session(), [_silence()] * 200])
    controller._recorder = recorder
    try:
        controller._start_turn(controller._run_voice_turn(), recording=True)
        assert await _wait_until(lambda: recorder.start_count == 2)
        assert controller._bar.state == "listening"
        assert controller._busy
    finally:
        await _finish(controller)


async def test_follow_up_idle_hides_bar(controller) -> None:
    controller._config.ui.follow_up_ms = 1000
    recorder = FakeRecorder([_vad_session(), [_silence()] * 4])
    controller._recorder = recorder
    controller._assistant._history.append({"role": "user", "content": "olá"})
    try:
        controller._start_turn(controller._run_voice_turn(), recording=True)
        assert await _wait_until(
            lambda: recorder.start_count == 2 and controller._bar.state == "hidden"
        )

        assert not controller._busy
        assert controller._assistant._history == []
        assert controller._bar._history == []
    finally:
        await _finish(controller)
