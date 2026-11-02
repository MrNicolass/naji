"""Wake word listener (openWakeWord).

Runs a low-power always-on microphone stream while the bar is hidden and idle.
When the configured wake word scores above the threshold, the listener invokes
its callback (from a worker thread) so the controller can open the bar and
start a VAD turn. The listener is disarmed while a turn is active or the bar
is visible, which also avoids re-triggering on Naji's own TTS.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from naji.config import Config
from naji.paths import asset_path

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms at 16 kHz
COOLDOWN_S = 3.0

# Official openWakeWord models bundled in assets/wakeword.
BUILTIN_MODELS = {
    "hey_jarvis": "hey_jarvis_v0.1.onnx",
    "alexa": "alexa_v0.1.onnx",
    "hey_mycroft": "hey_mycroft_v0.1.onnx",
}


class WakeWordError(RuntimeError):
    """Raised when the wake word engine cannot be loaded."""


def resolve_wakeword_models(word: str) -> tuple[Path, Path, Path] | None:
    """Resolve (wakeword, melspectrogram, embedding) model paths.

    ``word`` is either a built-in model name or a path to a custom ``.onnx``
    file. Returns ``None`` when it cannot be resolved.
    """
    mel = asset_path("wakeword", "melspectrogram.onnx")
    emb = asset_path("wakeword", "embedding_model.onnx")
    if not mel.exists() or not emb.exists():
        return None
    name = word.strip().lower()
    if name in BUILTIN_MODELS:
        wakeword = asset_path("wakeword", BUILTIN_MODELS[name])
    else:
        candidate = Path(word).expanduser()
        is_path = candidate.is_absolute() or candidate.suffix == ".onnx" or (
            candidate.parts and len(candidate.parts) > 1
        )
        if not is_path:
            return None
        wakeword = candidate
    return (wakeword, mel, emb) if wakeword.exists() else None


class WakeWordEngine:
    """Lazy wrapper around an openWakeWord model."""

    def __init__(self, models: tuple[Path, Path, Path]) -> None:
        self._models = models
        self._model: Any = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> Any:
        with self._lock:
            if self._model is None:
                from openwakeword.model import Model

                wakeword, mel, emb = self._models
                self._model = Model(
                    wakeword_models=[str(wakeword)],
                    melspec_model_path=str(mel),
                    embedding_model_path=str(emb),
                )
            return self._model

    def load(self) -> None:
        """Load the ONNX sessions (run in a worker thread)."""
        self._ensure_model()

    def reset(self) -> None:
        """Clear the model's internal feature/prediction buffers.

        The openWakeWord model is stateful: after a detection its buffers are
        primed with the wake phrase, so feeding silence (or stale frames) can
        keep scoring high. Reset before each listening session.
        """
        with self._lock:
            if self._model is not None:
                self._model.reset()

    def predict(self, chunk: np.ndarray) -> float:
        """Score one 16 kHz int16 frame (0.0-1.0)."""
        model = self._ensure_model()
        scores = model.predict(np.asarray(chunk, dtype=np.int16))
        return float(max(scores.values())) if scores else 0.0


class WakeWordListener:
    """Streams the microphone and reports wake word detections."""

    def __init__(
        self,
        config: Config,
        *,
        engine: WakeWordEngine | None = None,
        on_detected: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._on_detected = on_detected
        self._stream: Any = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._active = False
        self._stop = threading.Event()
        self._session = 0
        self._last_detection = 0.0

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> bool:
        if self._active:
            return True
        models = resolve_wakeword_models(self._config.wake.word)
        if models is None:
            log.warning("Wake word model not found for %r", self._config.wake.word)
            return False
        if self._engine is None:
            self._engine = WakeWordEngine(models)
        # Drop frames left over from the previous session: replaying them
        # through the (still primed) model caused false re-detections.
        self._drain_queue()
        self._last_detection = 0.0
        self._session += 1
        session = self._session
        self._stop.clear()
        self._active = True
        self._thread = threading.Thread(
            target=self._run,
            args=(session,),
            name="naji-wakeword",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        self._session += 1  # invalidate any running worker thread
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _run(self, session: int) -> None:
        import sounddevice as sd

        stream = None
        try:
            self._engine.load()
            if self._stop.is_set() or session != self._session:
                return
            # Fresh state: the model buffers still hold the previous
            # session's wake phrase and would keep scoring high.
            self._engine.reset()
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=FRAME_SAMPLES,
                dtype="int16",
                channels=1,
                device=self._config.audio.input_device,
                callback=self._callback,
            )
            self._stream = stream
            stream.start()
            log.info(
                "Wake word listening (word=%s, threshold=%.2f)",
                self._config.wake.word,
                self._config.wake.threshold,
            )
            while not self._stop.is_set() and session == self._session:
                try:
                    frame = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                score = self._engine.predict(frame)
                if score >= self._config.wake.threshold:
                    now = time.monotonic()
                    if now - self._last_detection < COOLDOWN_S:
                        continue
                    self._last_detection = now
                    log.info("Wake word detected (score=%.2f)", score)
                    if self._on_detected is not None:
                        self._on_detected()
        except Exception:
            if not self._stop.is_set():
                log.exception("Wake word listener failed")
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    log.debug("Could not close wake word stream", exc_info=True)
            if self._stream is stream:
                self._stream = None

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        if status:
            log.debug("Wake word stream status: %s", status)
        if not self._active:
            return
        chunk = np.asarray(indata[:, 0], dtype=np.int16).copy()
        self._queue.put(chunk)
