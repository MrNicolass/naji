"""Push-to-talk capture tests (no real audio device)."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from naji.config import AudioConfig
from naji.core.capture import CaptureError, PushToTalkRecorder, SpeechActivity, enough_audio


class FakeStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
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
        self.fail = False

    def InputStream(self, **kwargs) -> FakeStream:  # noqa: N802 (sounddevice API)
        if self.fail:
            raise OSError("no input device")
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


@pytest.fixture
def fake_sd(monkeypatch) -> FakeSoundDevice:
    fake = FakeSoundDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


def test_recorder_collects_chunks(fake_sd: FakeSoundDevice) -> None:
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.reset()
    recorder.start()
    stream = fake_sd.streams[0]
    stream.emit([100, -100])
    stream.emit([200])

    samples = recorder.stop()

    assert samples.tolist() == [100, -100, 200]
    assert stream.started and stream.stopped and stream.closed
    assert not recorder.is_active


def test_recorder_cancel_discards(fake_sd: FakeSoundDevice) -> None:
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.reset()
    recorder.start()
    fake_sd.streams[0].emit([10, 20])
    recorder.cancel()

    assert not recorder.is_active
    assert recorder.stop().size == 0


def test_recorder_start_failure(fake_sd: FakeSoundDevice) -> None:
    fake_sd.fail = True
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.reset()
    with pytest.raises(CaptureError):
        recorder.start()


def test_recorder_aborts_before_start(fake_sd: FakeSoundDevice) -> None:
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.reset()
    recorder.cancel()
    with pytest.raises(CaptureError):
        recorder.start()
    assert fake_sd.streams == []


def test_recorder_reset_clears_abort(fake_sd: FakeSoundDevice) -> None:
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.cancel()
    recorder.reset()
    recorder.start()
    assert recorder.is_active
    recorder.cancel()


def test_enough_audio() -> None:
    rate = 16000
    assert enough_audio(np.full(rate // 2, 100, dtype=np.int16), rate, 300)
    assert not enough_audio(np.full(100, 100, dtype=np.int16), rate, 300)
    assert not enough_audio(np.zeros(rate // 2, dtype=np.int16), rate, 300)
    assert enough_audio(np.zeros(rate // 2, dtype=np.int16), rate, 300, min_rms=0.0)


def test_recorder_take_chunk(fake_sd: FakeSoundDevice) -> None:
    recorder = PushToTalkRecorder(AudioConfig())
    recorder.reset()
    recorder.start()
    fake_sd.streams[0].emit([100, -100])

    chunk = recorder.take_chunk(0.1)
    assert chunk is not None
    assert chunk.tolist() == [100, -100]
    assert recorder.take_chunk(0.05) is None

    samples = recorder.stop()
    assert samples.tolist() == [100, -100]


def test_speech_activity_detects_end_of_phrase() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=500,
    )
    vad = SpeechActivity(config)
    rate = 16000
    silence = np.zeros(rate // 10, dtype=np.int16)
    speech = np.full(rate // 10, 1500, dtype=np.int16)

    for _ in range(3):
        assert vad.feed(silence) is None
    for _ in range(3):
        assert vad.feed(speech) is None
    trim = None
    for index in range(7):
        trim = vad.feed(silence)
        if index < 6:
            assert trim is None
    assert trim == 0


def test_speech_activity_keeps_pre_roll() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=500,
    )
    vad = SpeechActivity(config)
    rate = 16000
    silence = np.zeros(rate // 10, dtype=np.int16)
    speech = np.full(rate // 10, 1500, dtype=np.int16)

    for _ in range(10):
        assert vad.feed(silence) is None
    for _ in range(3):
        assert vad.feed(speech) is None
    trim = None
    for _ in range(7):
        trim = vad.feed(silence)
    assert trim == rate // 10 * 5


def test_speech_activity_adapts_to_quiet_microphone() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=0,
    )
    vad = SpeechActivity(config)
    rate = 16000
    silence = np.zeros(rate // 10, dtype=np.int16)
    quiet_speech = np.full(rate // 10, 300, dtype=np.int16)

    for _ in range(5):
        assert vad.feed(silence) is None
    for _ in range(3):
        assert vad.feed(quiet_speech) is None
    trim = None
    for _ in range(7):
        trim = vad.feed(silence)
    assert trim == rate // 10 * 5


def test_speech_activity_caps_threshold_at_configured_value() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=0,
    )
    vad = SpeechActivity(config)
    rate = 16000
    noisy_room = np.full(rate // 10, 200, dtype=np.int16)
    soft_speech = np.full(rate // 10, 400, dtype=np.int16)

    for _ in range(10):
        assert vad.feed(noisy_room) is None
    for _ in range(3):
        assert vad.feed(soft_speech) is None
    for _ in range(10):
        assert vad.feed(noisy_room) is None


def test_speech_activity_requires_min_speech() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=0,
    )
    vad = SpeechActivity(config)
    rate = 16000
    silence = np.zeros(rate // 10, dtype=np.int16)
    speech = np.full(rate // 10, 1500, dtype=np.int16)

    assert vad.feed(speech) is None
    for _ in range(10):
        assert vad.feed(silence) is None


def test_speech_activity_exposes_speech_started() -> None:
    config = AudioConfig(
        vad_threshold=0.5,
        vad_min_speech_ms=180,
        vad_silence_ms=700,
        vad_pre_roll_ms=0,
    )
    vad = SpeechActivity(config)
    rate = 16000
    silence = np.zeros(rate // 10, dtype=np.int16)
    speech = np.full(rate // 10, 1500, dtype=np.int16)

    assert not vad.speech_started
    for _ in range(10):  # calibration window
        vad.feed(silence)
    assert not vad.speech_started
    vad.feed(speech)
    assert vad.speech_started
