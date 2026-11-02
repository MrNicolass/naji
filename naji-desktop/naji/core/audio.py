"""Áudio nativo: sounddevice I/O, VAD (Silero), resampling, barge-in, jitter buffer."""

from __future__ import annotations

import asyncio
import collections
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import sounddevice as sd


@dataclass
class AudioConfig:
    sample_rate_in: int = 16000
    sample_rate_out: int = 24000
    chunk_ms: int = 30
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 180
    vad_pre_roll_ms: int = 500
    barge_in_enabled: bool = True
    jitter_buffer_ms: int = 100
    device_in: int | None = None
    device_out: int | None = None


class SileroVAD:
    """Wrapper para Silero VAD (onnxruntime)."""

    def __init__(self, threshold: float = 0.5, sample_rate: int = 16000) -> None:
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._model = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            import onnxruntime as ort

            # Silero VAD modelo mais leve (~1MB)
            # Baixar de: https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
            model_path = "silero_vad.onnx"
            self._model = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        except Exception:
            # Fallback: VAD simples baseado em energia
            self._model = None

    def __call__(self, audio_chunk: np.ndarray) -> float:
        """Retorna probabilidade de fala (0.0-1.0)."""
        if self._model is None:
            # Fallback simples: RMS normalizado
            rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
            return min(1.0, rms / 5000.0)  # Threshold empírico

        # Silero VAD espera chunks de 512 samples @ 16kHz (32ms)
        # Pad/truncate se necessário
        chunk = audio_chunk.astype(np.float32) / 32768.0
        if len(chunk) != 512:
            if len(chunk) > 512:
                chunk = chunk[:512]
            else:
                chunk = np.pad(chunk, (0, 512 - len(chunk)))

        # Silero input: [batch, samples]
        input_data = chunk.reshape(1, -1)
        try:
            outputs = self._model.run(None, {"input": input_data, "sr": np.array([self.sample_rate], dtype=np.int64)})
            return float(outputs[0][0][0])  # Probabilidade de fala
        except Exception:
            return 0.0


class AudioCapture:
    """
    Captura de áudio com VAD e barge-in.
    Roda em thread separada via sounddevice callback.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self.vad = SileroVAD(config.vad_threshold, config.sample_rate_in)
        self._stream: sd.InputStream | None = None
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._recording = False
        self._speech_detected = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._pre_roll_buffer: collections.deque[np.ndarray] = collections.deque(
            maxlen=config.vad_pre_roll_ms // config.chunk_ms
        )
        self._on_speech_start: Callable[[], None] | None = None
        self._on_speech_end: Callable[[np.ndarray], None] | None = None
        self._on_barge_in: Callable[[], None] | None = None

    def set_callbacks(
        self,
        on_speech_start: Callable[[], None] | None = None,
        on_speech_end: Callable[[np.ndarray], None] | None = None,
        on_barge_in: Callable[[], None] | None = None,
    ) -> None:
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_barge_in = on_barge_in

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Inicia captura. Deve ser chamado no event loop principal."""
        if self._recording:
            return
        self._loop = loop
        self._recording = True
        self._speech_detected = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._pre_roll_buffer.clear()

        blocksize = self.config.sample_rate_in * self.config.chunk_ms // 1000
        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate_in,
            blocksize=blocksize,
            dtype="int16",
            channels=1,
            device=self.config.device_in,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            print(f"AudioCapture status: {status}")

        chunk = indata[:, 0].copy()  # Mono

        # Pre-roll buffer
        self._pre_roll_buffer.append(chunk)

        if not self._recording:
            return

        # VAD
        speech_prob = self.vad(chunk)
        is_speech = speech_prob >= self.config.vad_threshold

        min_speech_frames = self.config.vad_min_speech_ms // self.config.chunk_ms

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0

            if not self._speech_detected and self._speech_frames >= min_speech_frames:
                # Início de fala detectado
                self._speech_detected = True
                # Enviar pre-roll + chunk atual
                pre_roll = np.concatenate(list(self._pre_roll_buffer)) if self._pre_roll_buffer else np.array([], dtype=np.int16)
                full_chunk = np.concatenate([pre_roll, chunk])
                if self._loop and self._on_speech_start:
                    self._loop.call_soon_threadsafe(self._on_speech_start)
                if self._loop:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, full_chunk)
        else:
            self._silence_frames += 1

            if self._speech_detected:
                # Ainda em fala, enviar chunk
                if self._loop:
                    self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)

                # Fim de fala detectado
                if self._silence_frames >= 3:  # ~90ms silêncio
                    self._speech_detected = False
                    self._speech_frames = 0
                    if self._loop and self._on_speech_end:
                        self._loop.call_soon_threadsafe(self._on_speech_end)

    async def get_audio(self) -> np.ndarray:
        """Aguarda e retorna próximo chunk de áudio."""
        return await self._queue.get()

    def is_recording(self) -> bool:
        return self._recording


class AudioPlayback:
    """
    Playback com jitter buffer para streaming de TTS.
    """

    def __init__(self, config: AudioConfig) -> None:
        self.config = config
        self._stream: sd.OutputStream | None = None
        self._buffer: collections.deque[np.ndarray] = collections.deque()
        self._buffer_lock = threading.Lock()
        self._playing = False
        self._underrun_count = 0

    def start(self) -> None:
        if self._playing:
            return
        self._playing = True
        blocksize = self.config.sample_rate_out * self.config.chunk_ms // 1000
        self._stream = sd.OutputStream(
            samplerate=self.config.sample_rate_out,
            blocksize=blocksize,
            dtype="int16",
            channels=1,
            device=self.config.device_out,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        self._playing = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._buffer_lock:
            self._buffer.clear()

    def write(self, chunk: np.ndarray) -> None:
        """Adiciona chunk PCM16 ao buffer de playback."""
        if chunk.dtype != np.int16:
            chunk = chunk.astype(np.int16)
        with self._buffer_lock:
            self._buffer.append(chunk)

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            print(f"AudioPlayback status: {status}")

        needed = frames
        out = np.zeros(frames, dtype=np.int16)
        written = 0

        with self._buffer_lock:
            while needed > 0 and self._buffer:
                chunk = self._buffer[0]
                take = min(needed, len(chunk))
                out[written:written + take] = chunk[:take]
                written += take
                needed -= take

                if take == len(chunk):
                    self._buffer.popleft()
                else:
                    self._buffer[0] = chunk[take:]

        if written < frames:
            self._underrun_count += 1

        outdata[:, 0] = out

    def get_buffered_ms(self) -> float:
        with self._buffer_lock:
            total_samples = sum(len(c) for c in self._buffer)
            return (total_samples / self.config.sample_rate_out) * 1000

    def clear(self) -> None:
        with self._buffer_lock:
            self._buffer.clear()


class BargeInDetector:
    """
    Detecta fala do usuário durante playback (barge-in).
    Monitora entrada enquanto reproduz.
    """

    def __init__(self, capture: AudioCapture, playback: AudioPlayback, config: AudioConfig) -> None:
        self.capture = capture
        self.playback = playback
        self.config = config
        self._active = False

    def enable(self, on_barge_in: Callable[[], None]) -> None:
        """Ativa detecção de barge-in."""
        self._active = True
        self.capture.set_callbacks(on_barge_in=on_barge_in)

    def disable(self) -> None:
        self._active = False
        self.capture.set_callbacks(on_barge_in=None)

    def is_active(self) -> bool:
        return self._active
