"""Push-to-talk capture.

The microphone stays closed until the user holds the hotkey. A single stream
collects PCM16 mono frames in the audio callback thread; the controller stops
and drains it on release. Blocking PortAudio calls must run in a worker thread.

In VAD mode the controller consumes chunks through :meth:`PushToTalkRecorder
.take_chunk` and feeds them to :class:`SpeechActivity`, which reports where a
spoken phrase ends.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

import numpy as np

from naji.config import AudioConfig

log = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    """Raised when the input stream cannot be opened."""


def enough_audio(samples: np.ndarray, rate: int, min_ms: int, *, min_rms: float = 4.0) -> bool:
    """Return whether a recording is long and loud enough to transcribe."""
    if rate <= 0 or samples.size == 0:
        return False
    duration_ms = (samples.size / rate) * 1000.0
    if duration_ms < min_ms:
        return False
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    return rms >= min_rms


class SpeechActivity:
    """Energy-based voice activity detector with an adaptive threshold.

    Tracks when the user starts and stops speaking. Instead of a fixed level,
    the threshold follows the ambient noise floor (4x the RMS of quiet
    chunks, clamped between 50 and ``vad_threshold * 1000``). That way quiet
    microphones are still detected, while a noisy room keeps the threshold
    high enough to ignore background sound.

    :meth:`feed` returns the number of leading samples to trim (pre-roll
    before speech) once a full phrase has ended, or ``None`` while the phrase
    is still open.
    """

    NOISE_FLOOR_START = 30.0
    NOISE_FLOOR_ALPHA = 0.1
    NOISE_FLOOR_MIN = 50.0
    NOISE_MULTIPLIER = 4.0
    CALIBRATION_MS = 300.0
    CALIBRATION_SPEECH_FACTOR = 8.0

    def __init__(self, config: AudioConfig) -> None:
        self._rate = max(1, config.sample_rate_in)
        self._max_threshold = max(self.NOISE_FLOOR_MIN, config.vad_threshold * 1000.0)
        self._min_speech_ms = float(config.vad_min_speech_ms)
        self._silence_ms = float(config.vad_silence_ms)
        self._pre_roll_samples = int(config.vad_pre_roll_ms * self._rate / 1000)
        self._noise_floor = self.NOISE_FLOOR_START
        self._calibration_ms = self.CALIBRATION_MS
        self._started = False
        self._speech_ms = 0.0
        self._silence_seen_ms = 0.0
        self._offset = 0
        self._speech_start = 0

    @property
    def samples_consumed(self) -> int:
        """Total PCM16 samples fed so far (for logging)."""
        return self._offset

    @property
    def speech_started(self) -> bool:
        """Whether any speech has been detected so far."""
        return self._started

    def _threshold(self) -> float:
        adaptive = self.NOISE_MULTIPLIER * self._noise_floor
        return max(self.NOISE_FLOOR_MIN, min(self._max_threshold, adaptive))

    def feed(self, chunk: np.ndarray) -> int | None:
        """Consume one PCM16 chunk; return the trim offset when speech ends."""
        data = np.asarray(chunk, dtype=np.int16).ravel()
        if not data.size:
            return None
        rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
        duration_ms = data.size / self._rate * 1000.0
        if self._calibration_ms > 0:
            # Measure the ambient level before trusting the threshold. A chunk
            # already far above the floor is speech, not noise: stop
            # calibrating and process it normally.
            self._calibration_ms -= duration_ms
            if rms >= self.CALIBRATION_SPEECH_FACTOR * self.NOISE_FLOOR_START:
                pass
            else:
                self._noise_floor = max(self._noise_floor, rms)
                self._offset += data.size
                return None
        threshold = self._threshold()
        if rms >= threshold:
            if not self._started:
                self._started = True
                self._speech_start = self._offset
            self._speech_ms += duration_ms
            self._silence_seen_ms = 0.0
        else:
            if self._started:
                self._silence_seen_ms += duration_ms
            self._noise_floor = (
                self.NOISE_FLOOR_ALPHA * rms
                + (1.0 - self.NOISE_FLOOR_ALPHA) * self._noise_floor
            )
        self._offset += data.size
        if (
            self._started
            and self._speech_ms >= self._min_speech_ms
            and self._silence_seen_ms >= self._silence_ms
        ):
            return max(0, self._speech_start - self._pre_roll_samples)
        return None


class PushToTalkRecorder:
    """Records a single push-to-talk turn into memory."""

    def __init__(self, config: AudioConfig) -> None:
        self._config = config
        self._stream: Any = None
        self._chunks: list[np.ndarray] = []
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._lock = threading.Lock()
        self._accepting = False
        self._active = False
        self._abort = threading.Event()
        self._dropped = 0

    @property
    def is_active(self) -> bool:
        return self._active

    def reset(self) -> None:
        """Prepare a fresh turn (must run before the start thread is spawned)."""
        with self._lock:
            self._abort.clear()
            self._accepting = False
            self._chunks = []
            self._dropped = 0
        self._drain_queue()

    def take_chunk(self, timeout: float | None = None) -> np.ndarray | None:
        """Wait for the next captured chunk (VAD mode). ``None`` when idle."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def start(self) -> None:
        with self._lock:
            if self._active:
                return
            if self._abort.is_set():
                raise CaptureError("capture cancelled")
            self._chunks = []
            self._dropped = 0
            self._accepting = True
        self._drain_queue()

        import sounddevice as sd

        blocksize = max(1, self._config.sample_rate_in * self._config.chunk_ms // 1000)
        stream = None
        try:
            stream = sd.InputStream(
                samplerate=self._config.sample_rate_in,
                blocksize=blocksize,
                dtype="int16",
                channels=1,
                device=self._config.input_device,
                callback=self._callback,
            )
            stream.start()
        except Exception as exc:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            with self._lock:
                self._accepting = False
                self._chunks = []
            raise CaptureError(f"could not open input stream: {type(exc).__name__}: {exc}") from exc

        with self._lock:
            aborted = self._abort.is_set()
            if not aborted:
                self._stream = stream
                self._active = True
        if aborted:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            with self._lock:
                self._accepting = False
                self._chunks = []
            raise CaptureError("capture cancelled")

        log.debug(
            "Recording started (device=%s, rate=%s)",
            self._config.input_device,
            self._config.sample_rate_in,
        )

    def stop(self) -> np.ndarray:
        """Stop the stream and return everything captured."""
        with self._lock:
            self._accepting = False
            self._active = False
            stream = self._stream
            self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                log.debug("Could not stop input stream", exc_info=True)
            try:
                stream.close()
            except Exception:
                log.debug("Could not close input stream", exc_info=True)

        self._drain_queue()
        with self._lock:
            chunks = self._chunks
            self._chunks = []
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks).astype(np.int16, copy=False)

    def cancel(self) -> None:
        with self._lock:
            self._abort.set()
            self._accepting = False
        self.stop()

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        if status:
            self._dropped += 1
            log.debug("Input stream status: %s", status)
        if not self._accepting:
            return
        chunk = np.asarray(indata[:, 0], dtype=np.int16).copy()
        with self._lock:
            if self._accepting:
                self._chunks.append(chunk)
                self._queue.put(chunk)
