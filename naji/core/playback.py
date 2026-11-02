"""Native audio playback for synthesized speech."""

from __future__ import annotations

import logging

import numpy as np

from naji.config import AudioConfig
from naji.core.realtime_client import resample_i16

log = logging.getLogger(__name__)


class AudioPlayer:
    """Plays PCM16 mono through sounddevice."""

    def __init__(self, config: AudioConfig) -> None:
        self._config = config

    def play(self, samples: np.ndarray, rate: int) -> None:
        import sounddevice as sd

        data = np.asarray(samples, dtype=np.int16)
        if data.size == 0:
            return
        if rate != self._config.sample_rate_out:
            data = resample_i16(data, rate, self._config.sample_rate_out)
        sd.play(
            data,
            self._config.sample_rate_out,
            device=self._config.output_device,
            blocking=True,
        )

    def stop(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            log.debug("Could not stop playback", exc_info=True)
