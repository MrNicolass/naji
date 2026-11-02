"""Wake word listener tests (no real audio device or model)."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

from naji.config import Config, WakeConfig
from naji.core.wakeword import WakeWordEngine, WakeWordListener, resolve_wakeword_models


class FakeStream:
    def __init__(self, **kwargs) -> None:
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def emit(self, values: list[int]) -> None:
        data = np.asarray(values, dtype=np.int16).reshape(-1, 1)
        self.callback(data, len(values), None, None)


class FakeSoundDevice:
    def __init__(self) -> None:
        self.streams: list[FakeStream] = []

    def InputStream(self, **kwargs) -> FakeStream:  # noqa: N802 (sounddevice API)
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


@pytest.fixture
def fake_sd(monkeypatch) -> FakeSoundDevice:
    fake = FakeSoundDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


class FakeModel:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls = 0

    def predict(self, x: np.ndarray) -> dict[str, float]:
        score = self.scores[min(self.calls, len(self.scores) - 1)]
        self.calls += 1
        return {"fake": score}


class FakeEngine:
    def __init__(self, scores: list[float], *, load_delay: float = 0.0) -> None:
        self._scores = scores
        self._model = FakeModel(scores)
        self._load_delay = load_delay
        self.loaded = False
        self.reset_count = 0

    def load(self) -> None:
        if self._load_delay:
            time.sleep(self._load_delay)
        self.loaded = True

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, chunk: np.ndarray) -> float:
        scores = self._model.predict(chunk)
        return float(max(scores.values()))


def _wait(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _config() -> Config:
    return Config(wake=WakeConfig(enabled=True, word="hey_jarvis", threshold=0.4))


def test_resolve_builtin_model() -> None:
    models = resolve_wakeword_models("hey_jarvis")
    assert models is not None
    wakeword, mel, emb = models
    assert wakeword.name == "hey_jarvis_v0.1.onnx"
    assert mel.name == "melspectrogram.onnx"
    assert emb.name == "embedding_model.onnx"
    assert wakeword.exists() and mel.exists() and emb.exists()


def test_resolve_unknown_model_returns_none() -> None:
    assert resolve_wakeword_models("naji") is None


def test_resolve_custom_path(tmp_path: Path) -> None:
    custom = tmp_path / "meu_modelo.onnx"
    custom.write_bytes(b"onnx")
    models = resolve_wakeword_models(str(custom))
    assert models is not None
    assert models[0] == custom


def test_engine_predict_uses_onnx_model(monkeypatch) -> None:
    package = types.ModuleType("openwakeword")
    model_mod = types.ModuleType("openwakeword.model")
    model_mod.Model = lambda **kwargs: FakeModel([0.7])
    package.model = model_mod
    monkeypatch.setitem(sys.modules, "openwakeword", package)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_mod)

    models = resolve_wakeword_models("hey_jarvis")
    assert models is not None
    engine = WakeWordEngine(models)
    score = engine.predict(np.zeros(1280, dtype=np.int16))
    assert score == 0.7


def test_listener_detects_wake_word(fake_sd) -> None:
    detected = threading.Event()
    engine = FakeEngine([0.1, 0.9, 0.9, 0.9])
    listener = WakeWordListener(
        _config(),
        engine=engine,
        on_detected=detected.set,
    )
    assert listener.start()
    assert _wait(lambda: fake_sd.streams and fake_sd.streams[0].started)
    stream = fake_sd.streams[0]

    stream.emit([0] * 1280)  # below threshold
    time.sleep(0.1)
    assert not detected.is_set()

    stream.emit([1000] * 1280)  # above threshold
    assert detected.wait(5.0)

    # Cooldown: the next high frame must not re-trigger immediately.
    detected.clear()
    stream.emit([1000] * 1280)
    time.sleep(0.3)
    assert not detected.is_set()

    listener.stop()
    assert stream.stopped and stream.closed
    assert not listener.is_active


def test_listener_start_fails_without_model(fake_sd) -> None:
    config = Config(wake=WakeConfig(enabled=True, word="naji", threshold=0.4))
    listener = WakeWordListener(config)
    assert not listener.start()
    assert not listener.is_active


def test_listener_ignores_stale_frames(fake_sd) -> None:
    """Frames left over from a previous session must not re-trigger."""
    detected = threading.Event()
    engine = FakeEngine([0.9, 0.9, 0.9])
    listener = WakeWordListener(
        _config(),
        engine=engine,
        on_detected=detected.set,
    )
    assert listener.start()
    assert _wait(lambda: fake_sd.streams and fake_sd.streams[0].started)
    fake_sd.streams[0].emit([1000] * 1280)
    assert detected.wait(5.0)
    listener.stop()

    # Simulate the tail of the wake phrase still queued at stop time.
    listener._queue.put(np.zeros(1280, dtype=np.int16))
    listener._queue.put(np.full(1280, 1000, dtype=np.int16))

    detected.clear()
    assert listener.start()
    assert _wait(lambda: len(fake_sd.streams) == 2 and fake_sd.streams[1].started)
    time.sleep(0.5)
    assert not detected.is_set()  # stale frames were drained, not replayed

    # The new session still reacts to fresh audio.
    fake_sd.streams[1].emit([1000] * 1280)
    assert detected.wait(5.0)
    listener.stop()


def test_listener_resets_model_between_sessions(fake_sd) -> None:
    engine = FakeEngine([0.1])
    listener = WakeWordListener(_config(), engine=engine)
    assert listener.start()
    assert _wait(lambda: fake_sd.streams and fake_sd.streams[0].started)
    listener.stop()
    assert engine.reset_count == 1
    assert listener.start()
    assert _wait(lambda: len(fake_sd.streams) == 2 and fake_sd.streams[1].started)
    listener.stop()
    assert engine.reset_count == 2


def test_listener_zombie_thread_does_not_listen(fake_sd) -> None:
    """A thread whose load outlived stop() must not open a second stream."""
    engine = FakeEngine([0.9], load_delay=2.2)
    listener = WakeWordListener(_config(), engine=engine)
    assert listener.start()
    time.sleep(0.1)
    listener.stop()  # join times out: the engine is still loading
    assert listener.start()
    assert _wait(lambda: fake_sd.streams and fake_sd.streams[0].started, timeout=10.0)
    time.sleep(0.3)
    assert len(fake_sd.streams) == 1
    listener.stop()


def test_wake_config_defaults() -> None:
    wake = WakeConfig()
    assert wake.enabled is False
    assert wake.word == "hey_jarvis"
    assert wake.threshold == 0.4
