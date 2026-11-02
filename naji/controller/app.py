"""Application controller.

Owns the wiring between tray, bar, hotkeys and the voice pipeline. Push-to-talk
opens the microphone only while the hotkey is held; on release the audio is
transcribed by the voice endpoint and shown in the bar.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from naji.config import Config
from naji.core.assistant import Assistant
from naji.core.capture import (
    CaptureError,
    PushToTalkRecorder,
    SpeechActivity,
    enough_audio,
)
from naji.core.playback import AudioPlayer
from naji.core.realtime_client import (
    pcm_f32_to_i16,
    rate_from_content_type,
    request_tts,
    transcribe_audio,
)
from naji.core.tools.notification import set_notifier
from naji.core.wakeword import WakeWordListener
from naji.i18n import Translator
from naji.platform.autostart import set_autostart
from naji.ui.bar import NajiBar, format_hotkey
from naji.ui.global_hotkey import GlobalHotkeyManager
from naji.ui.settings import SettingsDialog
from naji.ui.theme import build_qss, get_tokens
from naji.ui.tray import NajiTray

log = logging.getLogger(__name__)


class _WakeBridge(QObject):
    """Marshals wake word detections from the listener thread to Qt."""

    detected = Signal()


class AppController(QObject):
    """Coordinates the long-lived desktop shell."""

    def __init__(
        self,
        app: QApplication,
        config: Config,
        config_path: Path,
        translator: Translator,
        bar: NajiBar,
        tray: NajiTray,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._config = config
        self._config_path = config_path
        self._t = translator
        self._bar = bar
        self._tray = tray
        self._muted = False
        self._shutting_down = False
        self._recorder = PushToTalkRecorder(config.audio)
        self._assistant = Assistant(config)
        self._player = AudioPlayer(config.audio)
        set_notifier(self._show_notification)
        self._stop_event = asyncio.Event()
        self._turn_task: asyncio.Task[None] | None = None
        self._confirmation_future: asyncio.Future[bool] | None = None
        self._ptt_down = False
        self._recording = False
        self._busy = False
        self._turn_seq = 0
        self._settings: SettingsDialog | None = None
        self._wake_turn = False
        self._wake_bridge = _WakeBridge(self)
        self._wake_bridge.detected.connect(self._on_wake_detected)
        self._wake: WakeWordListener | None = (
            WakeWordListener(config, on_detected=self._wake_bridge.detected.emit)
            if config.wake.enabled
            else None
        )

        self._hotkeys = GlobalHotkeyManager(config, self)
        self._wire()

    # ------------------------------------------------------------------ setup
    def _wire(self) -> None:
        self._bar.stop_requested.connect(self._on_stop)
        self._bar.mute_toggled.connect(self._set_muted)
        self._bar.history_requested.connect(self._on_history)
        self._bar.text_submitted.connect(self._on_text_submitted)
        self._bar.confirmation_answered.connect(self._on_confirmation_answered)
        self._bar.settings_requested.connect(self._on_settings)
        self._bar.new_requested.connect(self._on_new_conversation)
        self._bar.hidden.connect(self._on_bar_hidden)

        self._tray.open_requested.connect(self.show_bar)
        self._tray.new_requested.connect(self._on_new_conversation)
        self._tray.mute_toggled.connect(self._set_muted)
        self._tray.settings_requested.connect(self._on_settings)
        self._tray.autostart_toggled.connect(self._on_autostart)
        self._tray.quit_requested.connect(self._quit)

        self._hotkeys.ptt_pressed.connect(self._on_ptt_pressed)
        self._hotkeys.ptt_released.connect(self._on_ptt_released)

    def start(self, *, announce: bool = True) -> None:
        self._tray.show()
        if not self._hotkeys.start():
            log.warning("Global hotkey %s could not be registered", self._config.ui.hotkey)
            QTimer.singleShot(400, self._warn_hotkey)
        else:
            log.info("Global hotkey backend: %s", self._hotkeys.backend_name)

        self._sync_wake_listener()
        if announce:
            QTimer.singleShot(800, self._announce_started)

    def _announce_started(self) -> None:
        self._tray.show_message(
            self._t.t("tray.message.started.title"),
            self._t.t(
                "tray.message.started.body",
                hotkey=format_hotkey(self._config.ui.hotkey),
            ),
        )

    def _warn_hotkey(self) -> None:
        self._tray.show_message(
            self._t.t("tray.message.hotkey_error.title"),
            self._t.t(
                "tray.message.hotkey_error.body",
                hotkey=format_hotkey(self._config.ui.hotkey),
            ),
            QSystemTrayIcon.Warning,
        )

    # ------------------------------------------------------------------- bar
    def show_bar(self) -> None:
        if self._busy:
            state = self._bar.state if self._bar.state != "hidden" else "summoned"
            self._bar.show_bar(state)
            return
        self._bar.show_bar("summoned")
        self._tray.set_state("standby")
        self._sync_wake_listener()

    # --------------------------------------------------------------- wake word
    def _sync_wake_listener(self) -> None:
        """Arm the wake word listener only while idle and the bar is hidden."""
        if self._wake is None:
            return
        want = not self._shutting_down and not self._busy and self._bar.state == "hidden"
        if want and not self._wake.is_active:
            if not self._wake.start():
                self._wake = None
        elif not want and self._wake.is_active:
            self._wake.stop()

    def _on_wake_detected(self) -> None:
        if self._shutting_down or self._busy:
            return
        self._wake_turn = True
        if not self._start_turn(self._run_voice_turn(), recording=True):
            self._wake_turn = False

    # ----------------------------------------------------------------- voice
    def _on_ptt_pressed(self) -> None:
        if self._shutting_down or self._ptt_down:
            return
        self._ptt_down = True
        if self._recording:
            # Toggle/VAD modes: a second press ends the current capture.
            log.info("PTT pressed during capture (mode=%s); ending capture", self._config.ui.speech_mode)
            self._stop_event.set()
            return
        if self._busy:
            if not self._barge_in_allowed():
                log.info(
                    "PTT pressed while busy (bar=%s); barge-in not allowed",
                    self._bar.state,
                )
                self._ptt_down = False
                return
            log.info("Barge-in: stopping playback and starting a new turn")
            self._player.stop()
        log.info(
            "PTT pressed (mode=%s, bar=%s); starting voice turn",
            self._config.ui.speech_mode,
            self._bar.state,
        )
        if not self._start_turn(self._run_voice_turn(), recording=True):
            self._ptt_down = False

    def _on_ptt_released(self) -> None:
        if not self._ptt_down:
            return
        self._ptt_down = False
        log.info(
            "PTT released (mode=%s, recording=%s, bar=%s)",
            self._config.ui.speech_mode,
            self._recording,
            self._bar.state,
        )
        if self._config.ui.speech_mode == "ptt":
            self._stop_event.set()

    def _barge_in_allowed(self) -> bool:
        return self._config.audio.barge_in_enabled and self._bar.state == "speaking"

    def _start_turn(self, coro, *, recording: bool = False) -> bool:
        self._turn_seq += 1
        self._stop_event.clear()
        if recording:
            self._recorder.reset()
        self._recording = recording
        self._busy = True
        task = self._spawn(coro)
        if task is None:
            self._recording = False
            self._busy = False
            self._sync_wake_listener()
            return False
        self._turn_task = task
        self._sync_wake_listener()
        return True

    def _spawn(self, coro) -> asyncio.Task[None] | None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            coro.close()
            log.warning("No running event loop; ignoring voice turn")
            return None
        return loop.create_task(coro)

    async def _run_voice_turn(self, *, follow_up: bool = False) -> None:
        seq = self._turn_seq
        task = asyncio.current_task()
        mode = self._config.ui.speech_mode
        self._bar.show_bar("listening")
        self._tray.set_state("listening")
        ok = False
        idle_hide = False
        try:
            try:
                await asyncio.to_thread(self._recorder.start)
            except CaptureError:
                log.exception("Could not open the microphone")
                self._fail("bar.error.mic")
                return
            except Exception:
                log.exception("Unexpected microphone error")
                self._fail("bar.error.audio")
                return

            trim = 0
            try:
                if mode == "vad" or self._wake_turn:
                    idle_timeout = (
                        self._config.ui.follow_up_ms / 1000.0 if follow_up else None
                    )
                    trim = await self._wait_for_speech_end(idle_timeout)
                else:
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._config.audio.max_record_s,
                        )
                    except TimeoutError:
                        log.info("Maximum recording length reached")
            finally:
                self._ptt_down = False

            if trim < 0:
                idle_hide = True
                return

            samples = await asyncio.to_thread(self._recorder.stop)
            if trim:
                samples = samples[trim:]
            if not enough_audio(
                samples,
                self._config.audio.sample_rate_in,
                self._config.audio.min_record_ms,
            ):
                log.info("Recording too short or silent")
                self._fail("bar.error.short")
                return

            self._bar.set_state("transcribing")
            self._tray.set_state("transcribing")
            try:
                text = await self._transcribe(samples)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Transcription failed")
                self._fail("bar.error.stt")
                return
            if not text:
                self._fail("bar.error.no_speech")
                return

            ok = await self._respond_to_text(text, seq)
        except asyncio.CancelledError:
            log.debug("Voice turn cancelled")
            raise
        except Exception:
            log.exception("Voice turn failed")
            self._fail("bar.error.reply")
        finally:
            if self._turn_task is task:
                try:
                    await asyncio.to_thread(self._recorder.cancel)
                except Exception:
                    log.debug("Could not cancel the microphone", exc_info=True)
                self._busy = False
                self._recording = False
                self._ptt_down = False
                self._wake_turn = False
                self._turn_task = None
                self._sync_wake_listener()
                if idle_hide:
                    self._bar.hide_bar()
                elif ok and mode == "vad" and not self._shutting_down:
                    self._start_follow_up()

    def _start_follow_up(self) -> None:
        """Keep listening so the conversation can continue (VAD mode)."""
        if self._shutting_down or self._busy:
            return
        log.info(
            "Follow-up listening started (window=%.0f ms)",
            self._config.ui.follow_up_ms,
        )
        self._start_turn(self._run_voice_turn(follow_up=True), recording=True)

    async def _wait_for_speech_end(self, idle_timeout_s: float | None = None) -> int:
        """Listen in VAD mode until a phrase ends; return samples to trim.

        Returns -1 when ``idle_timeout_s`` elapses without any speech (the
        follow-up listening window ending the session quietly).
        """
        detector = SpeechActivity(self._config.audio)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._config.audio.max_record_s
        idle_deadline = (
            loop.time() + idle_timeout_s if idle_timeout_s is not None else None
        )
        while loop.time() < deadline:
            if self._stop_event.is_set():
                return 0
            chunk = await asyncio.to_thread(self._recorder.take_chunk, 0.25)
            if (
                idle_deadline is not None
                and not detector.speech_started
                and loop.time() >= idle_deadline
            ):
                log.info("Follow-up window elapsed without speech")
                return -1
            if chunk is None:
                continue
            trim = detector.feed(chunk)
            if trim is not None:
                duration = detector.samples_consumed / self._config.audio.sample_rate_in
                log.info("VAD ended the phrase after %.1f s", duration)
                return trim
        log.info("VAD reached the maximum recording length")
        return 0

    async def _respond_to_text(self, text: str, seq: int) -> bool:
        display = self._shorten(text)
        self._bar.set_state(
            "thinking",
            title=display,
            hint=self._t.t("bar.thinking.hint"),
            tooltip=text,
        )
        self._tray.set_state("thinking")
        try:
            reply = await self._assistant.reply(
                text,
                on_tool=self._on_tool,
                on_confirmation=self._confirm_tool,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Assistant failed")
            self._fail("bar.error.reply")
            return False
        if not reply:
            self._fail("bar.error.reply")
            return False

        self._bar.set_history(self._assistant.history)
        await self._speak(reply, seq)
        return seq == self._turn_seq

    async def _transcribe(self, samples: np.ndarray) -> str:
        language = None
        if self._config.ui.locale == "pt-BR":
            language = "pt"
        elif self._config.ui.locale == "en":
            language = "en"
        text = await transcribe_audio(
            self._config.server.voice_endpoint,
            self._config.server.api_key,
            self._config.models.voice_model,
            samples,
            self._config.audio.sample_rate_in,
            language=language,
            timeout=self._config.server.transcribe_timeout_s,
        )
        text = text.strip()
        log.info(
            "Transcribed %.1f s of audio into %d characters",
            samples.size / self._config.audio.sample_rate_in,
            len(text),
        )
        return text

    def _on_tool(self, name: str) -> None:
        key = f"bar.tool.{name}"
        label = self._t.t(key)
        self._bar.set_state("acting", hint=label if label != key else name)
        self._tray.set_state("acting")

    def _show_notification(self, title: str, message: str, kind: str) -> None:
        icon = {
            "info": QSystemTrayIcon.Information,
            "success": QSystemTrayIcon.Information,
            "warning": QSystemTrayIcon.Warning,
            "error": QSystemTrayIcon.Critical,
        }.get(kind, QSystemTrayIcon.Information)
        self._tray.show_message(title, message, icon)

    async def _confirm_tool(self, name: str, arguments: dict[str, object], key: str) -> bool:
        """Wait for an explicit in-bar decision before a destructive tool runs."""
        future = asyncio.get_running_loop().create_future()
        self._confirmation_future = future
        self._bar.show_bar("confirming")
        target = arguments.get("app") or arguments.get("title") or arguments.get("path") or name
        self._bar.show_confirmation(self._t.t(key, tool=target))
        self._tray.set_state("confirming")
        try:
            return await future
        finally:
            if self._confirmation_future is future:
                self._confirmation_future = None

    def _on_confirmation_answered(self, allowed: bool) -> None:
        future = self._confirmation_future
        if future is not None and not future.done():
            future.set_result(allowed)
        self._bar.set_state("thinking")
        self._tray.set_state("thinking")

    async def _speak(self, reply: str, seq: int) -> None:
        display = self._shorten(reply)
        if not self._muted:
            self._bar.set_state(
                "speaking",
                title=display,
                hint=self._t.t(
                    "bar.speaking.hint",
                    hotkey=format_hotkey(self._config.ui.hotkey),
                ),
                tooltip=reply,
            )
            self._tray.set_state("speaking")
            try:
                data, content_type = await request_tts(
                    self._config.server.voice_endpoint,
                    self._config.server.api_key,
                    text=reply,
                    voice="female",
                    lang="en" if self._config.ui.locale == "en" else "pt",
                    response_format="pcm",
                    stream=True,
                    timeout=120.0,
                )
                samples = pcm_f32_to_i16(data)
                if samples.size:
                    rate = rate_from_content_type(content_type)
                    await asyncio.to_thread(self._player.play, samples, rate)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("TTS playback failed")
        if seq != self._turn_seq:
            return
        self._bar.set_state(
            "done",
            title=display,
            hint=self._t.t(
                "bar.done.hint",
                hotkey=format_hotkey(self._config.ui.hotkey),
            ),
            tooltip=reply,
            timeout_ms=self._config.ui.follow_up_ms,
        )
        self._tray.set_state("done")

    @staticmethod
    def _shorten(text: str, limit: int = 36) -> str:
        display = text.strip()
        if len(display) > limit:
            display = display[: limit - 1].rstrip() + "…"
        return display

    def _fail(self, key: str) -> None:
        self._bar.show_bar("error")
        self._bar.set_state("error", hint=self._t.t(key))
        self._tray.set_state("error")

    def _cancel_turn(self) -> None:
        self._turn_seq += 1
        self._ptt_down = False
        self._stop_event.set()
        self._player.stop()
        if self._confirmation_future is not None and not self._confirmation_future.done():
            self._confirmation_future.set_result(False)
        if self._turn_task is not None and not self._turn_task.done():
            self._turn_task.cancel()

    def _on_stop(self) -> None:
        if self._shutting_down:
            return
        self._cancel_turn()
        self._bar.set_state("done", hint=self._t.t("bar.stopped"))
        self._tray.set_state("standby")
        QTimer.singleShot(600, self._hide_done_bar)

    def _hide_done_bar(self) -> None:
        if self._bar.state == "done":
            self._bar.hide_bar()

    def _on_bar_hidden(self) -> None:
        if self._ptt_down or self._busy:
            log.info("Bar hidden during an active turn (bar=%s); cancelling", self._bar.state)
            self._cancel_turn()
        # A hidden bar ends the session: the next one starts fresh.
        self._assistant.reset()
        self._bar.set_history([])
        self._tray.set_state("standby")
        self._sync_wake_listener()

    # --------------------------------------------------------------- actions
    def _set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._bar.set_muted(muted)
        self._tray.set_muted(muted)

    def _on_history(self) -> None:
        self._bar.set_history(self._assistant.history)
        self._bar.toggle_history()

    def _on_text_submitted(self, text: str) -> None:
        if self._shutting_down or self._busy or not text.strip():
            return
        self._start_turn(self._run_text_turn(text))

    async def _run_text_turn(self, text: str) -> None:
        seq = self._turn_seq
        task = asyncio.current_task()
        try:
            await self._respond_to_text(text, seq)
        except asyncio.CancelledError:
            log.debug("Text turn cancelled")
            raise
        except Exception:
            log.exception("Text turn failed")
            self._fail("bar.error.reply")
        finally:
            if self._turn_task is task:
                self._busy = False
                self._turn_task = None

    def _on_settings(self) -> None:
        if self._settings is None:
            self._settings = SettingsDialog(self._config, self._t)
            self._settings.saved.connect(self._apply_settings)
            self._settings.finished.connect(self._clear_settings)
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _clear_settings(self, _result: int) -> None:
        self._settings = None

    def _apply_settings(self) -> None:
        try:
            set_autostart(self._config.ui.start_with_windows)
        except OSError:
            log.exception("Could not change autostart from settings")
            self._tray.show_message(
                self._t.t("settings.title"),
                self._t.t("tray.message.autostart.error"),
                QSystemTrayIcon.Warning,
            )

        self._t.set_locale(self._config.ui.locale)
        tokens = get_tokens(self._config.ui.theme)
        self._app.setStyleSheet(build_qss(tokens))
        self._bar.apply_theme(tokens)
        self._bar.set_reduced_motion(self._config.ui.reduced_motion)
        self._bar.retranslate(self._t)
        self._tray.set_tokens(tokens)
        self._tray.retranslate(self._t)
        self._tray.set_autostart(self._config.ui.start_with_windows)
        try:
            self._config.save_yaml(self._config_path)
        except OSError:
            log.exception("Could not persist config to %s", self._config_path)

    def _on_new_conversation(self) -> None:
        self._cancel_turn()
        self._assistant.reset()
        self._bar.clear_history()
        self._bar.show_bar("summoned")
        self._tray.show_message(
            self._t.t("tray.message.new.title"),
            self._t.t("tray.message.new.body"),
        )

    def _on_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError:
            log.exception("Could not change autostart to %s", enabled)
            self._tray.set_autostart(not enabled)
            self._tray.show_message(
                self._t.t("tray.message.settings.title"),
                self._t.t("tray.message.autostart.error"),
                QSystemTrayIcon.Warning,
            )
            return

        self._config.ui.start_with_windows = enabled
        try:
            self._config.save_yaml(self._config_path)
        except OSError:
            log.exception("Could not persist config to %s", self._config_path)

        self._tray.set_autostart(enabled)
        self._tray.show_message(
            self._t.t("app.name"),
            self._t.t("tray.message.autostart.on" if enabled else "tray.message.autostart.off"),
        )

    # ------------------------------------------------------------------ quit
    def _quit(self) -> None:
        self.shutdown()
        self._app.quit()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._cancel_turn()
        self._hotkeys.stop()
        if self._wake is not None:
            self._wake.stop()
        self._player.stop()
        try:
            self._recorder.cancel()
        except Exception:
            log.debug("Could not close the microphone on shutdown", exc_info=True)
        self._tray.hide()
        self._bar.hide()
