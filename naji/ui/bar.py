"""Floating command bar.

A frameless, always-on-top tool window centered above the taskbar. It has no
taskbar entry and hides itself when it loses focus or after an idle timeout.
"""

from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from naji.config import Config
from naji.i18n import Translator
from naji.ui.theme.tokens import BAR, FONT_SANS_FAMILY, MOTION, SPACE

STATE_KEYS = {
    "summoned": ("bar.summoned.title", "bar.summoned.hint"),
    "listening": ("bar.listening.title", "bar.listening.hint"),
    "transcribing": ("bar.transcribing.title", "bar.transcribing.hint"),
    "thinking": ("bar.thinking.title", "bar.thinking.hint"),
    "acting": ("bar.acting.title", "bar.acting.hint"),
    "speaking": ("bar.speaking.title", "bar.speaking.hint"),
    "done": ("bar.done.title", "bar.done.hint"),
    "error": ("bar.error.title", "bar.error.hint"),
}

_AUTO_HIDE_STATES = {"summoned", "done", "error"}
_ACTIVE_STATES = {"listening", "transcribing", "thinking", "acting", "speaking"}


def format_hotkey(value: str) -> str:
    parts = [part.strip() for part in value.split("+") if part.strip()]
    return "+".join(part[:1].upper() + part[1:] for part in parts)


class NajiOrb(QWidget):
    """Brand orb that animates while Naji listens or speaks."""

    def __init__(self, tokens: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._state = "standby"
        self._phase = 0.0
        self._reduced_motion = False
        self.setFixedSize(36, 36)

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self.update()

    def set_state(self, state: str) -> None:
        self._state = state
        if state in _ACTIVE_STATES and not self._reduced_motion:
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def set_reduced_motion(self, reduced: bool) -> None:
        self._reduced_motion = reduced
        if reduced:
            self._timer.stop()
            self._phase = 0.0
            self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.08) % 1.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(3, 3, 30, 30)
        state = self._state
        tokens = self._tokens

        if state in _ACTIVE_STATES:
            pulse = self._phase
            ring = QRectF(
                3 - pulse * 3,
                3 - pulse * 3,
                30 + pulse * 6,
                30 + pulse * 6,
            )
            ring_color = QColor(tokens["accent"])
            ring_color.setAlphaF(0.35 * (1.0 - pulse))
            painter.setPen(QPen(ring_color, 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ring)

            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor(tokens["gradient_start"]))
            gradient.setColorAt(0.55, QColor(tokens["gradient_mid"]))
            gradient.setColorAt(1.0, QColor(tokens["gradient_end"]))
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
        else:
            color = QColor(
                tokens["danger"] if state in ("error", "disconnected") else tokens["accent"]
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)

        painter.drawEllipse(rect)
        painter.setPen(QColor(tokens["on_accent"]))
        painter.setFont(QFont(FONT_SANS_FAMILY, 12, QFont.Weight.DemiBold))
        painter.drawText(rect, Qt.AlignCenter, "N")
        painter.end()


class NajiBar(QWidget):
    """The floating command bar."""

    stop_requested = Signal()
    mute_toggled = Signal(bool)
    history_requested = Signal()
    text_submitted = Signal(str)
    confirmation_answered = Signal(bool)
    settings_requested = Signal()
    new_requested = Signal()
    hidden = Signal()

    def __init__(
        self,
        config: Config,
        translator: Translator,
        tokens: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("Naji")
        self.setFixedSize(BAR["width"], BAR["input_height"])

        self._config = config
        self._t = translator
        self._tokens = tokens
        self._state = "hidden"
        self._muted = False
        self._hotkey = format_hotkey(config.ui.hotkey)
        self._hiding = False
        self._shown_at = 0.0
        self._hide_after_ms: int | None = None
        self._history_visible = False
        self._history: list[dict[str, Any]] = []
        self._confirmation_visible = False

        self._build_ui()

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(MOTION["fast"])
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_bar)

        self._orb.set_reduced_motion(config.ui.reduced_motion)

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self._surface = QFrame(self)
        self._surface.setObjectName("NajiBarSurface")
        # Can hold focus (harmless) so buttons never do while the bar is
        # active; ClickFocus keeps it out of the tab order.
        self._surface.setFocusPolicy(Qt.ClickFocus)
        outer.addWidget(self._surface)

        shadow = QGraphicsDropShadowEffect(self._surface)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 105))
        self._surface.setGraphicsEffect(shadow)

        surface_layout = QVBoxLayout(self._surface)
        surface_layout.setContentsMargins(0, 0, 0, 0)
        surface_layout.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(SPACE["xl"], SPACE["md"], SPACE["md"], SPACE["md"])
        content.setSpacing(SPACE["md"])

        self._orb = NajiOrb(self._tokens, self._surface)
        content.addWidget(self._orb, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)

        self._title = QLabel(self._surface)
        self._title.setProperty("role", "title")
        self._title.setWordWrap(False)
        self._title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._title.setMinimumWidth(120)

        self._hint = QLabel(self._surface)
        self._hint.setProperty("role", "secondary")
        self._hint.setWordWrap(False)
        self._hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._hint.setMinimumWidth(120)

        text.addWidget(self._title)
        text.addWidget(self._hint)
        content.addLayout(text, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(SPACE["xs"])

        self._stop_btn = self._make_button(self._t.t("bar.stop"), role="danger")
        self._stop_btn.clicked.connect(lambda: self.stop_requested.emit())
        self._stop_btn.hide()
        controls.addWidget(self._stop_btn)

        self._mute_btn = self._make_button(self._t.t("bar.mute.short"), checkable=True)
        self._mute_btn.toggled.connect(self._on_mute_toggled)
        controls.addWidget(self._mute_btn)

        self._history_btn = self._make_button(self._t.t("bar.history"), checkable=True)
        self._history_btn.clicked.connect(lambda: self.history_requested.emit())
        self._history_btn.setVisible(self._config.ui.history_enabled)
        controls.addWidget(self._history_btn)

        self._new_btn = self._make_button(self._t.t("bar.new.short"))
        self._new_btn.setToolTip(self._t.t("bar.new"))
        self._new_btn.setAccessibleName(self._t.t("bar.new"))
        self._new_btn.clicked.connect(lambda: self.new_requested.emit())
        controls.addWidget(self._new_btn)

        self._settings_btn = self._make_button(self._t.t("bar.settings"))
        self._settings_btn.clicked.connect(lambda: self.settings_requested.emit())
        controls.addWidget(self._settings_btn)

        self._close_btn = self._make_button("×", object_name="NajiClose")
        self._close_btn.setToolTip(self._t.t("bar.close"))
        self._close_btn.setAccessibleName(self._t.t("bar.close"))
        self._close_btn.clicked.connect(lambda: self.hide_bar())
        controls.addWidget(self._close_btn)

        content.addLayout(controls)
        surface_layout.addLayout(content)

        self._input_row = QHBoxLayout()
        self._input_row.setContentsMargins(SPACE["xl"], 0, SPACE["md"], SPACE["md"])
        self._input_row.setSpacing(SPACE["sm"])

        self._text_input = QLineEdit(self._surface)
        self._text_input.setPlaceholderText(self._t.t("bar.input.placeholder"))
        self._text_input.setAccessibleName(self._t.t("bar.input.placeholder"))
        self._text_input.returnPressed.connect(self._submit_text)
        self._text_input.textChanged.connect(self._restart_hide_timer)
        self._text_input.installEventFilter(self)
        self._input_row.addWidget(self._text_input, 1)

        self._send_btn = self._make_button(self._t.t("bar.input.send"), role="accent")
        self._send_btn.clicked.connect(self._submit_text)
        self._input_row.addWidget(self._send_btn)

        self._confirm_btn = self._make_button(self._t.t("bar.confirming.yes"), role="accent")
        self._confirm_btn.setFocusPolicy(Qt.StrongFocus)
        self._confirm_btn.clicked.connect(lambda: self._answer_confirmation(True))
        self._confirm_btn.hide()
        self._input_row.addWidget(self._confirm_btn)

        self._deny_btn = self._make_button(self._t.t("bar.confirming.no"))
        self._deny_btn.setFocusPolicy(Qt.StrongFocus)
        self._deny_btn.clicked.connect(lambda: self._answer_confirmation(False))
        self._deny_btn.hide()
        self._input_row.addWidget(self._deny_btn)
        surface_layout.addLayout(self._input_row)

        self._history_panel = QScrollArea(self._surface)
        self._history_panel.setObjectName("NajiHistory")
        self._history_panel.setWidgetResizable(True)
        self._history_panel.setFrameShape(QFrame.NoFrame)
        self._history_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._history_panel.setAccessibleName(self._t.t("bar.history.panel"))

        self._history_content = QWidget(self._history_panel)
        self._history_layout = QVBoxLayout(self._history_content)
        self._history_layout.setContentsMargins(SPACE["xl"], SPACE["sm"], SPACE["xl"], SPACE["md"])
        self._history_layout.setSpacing(SPACE["sm"])
        self._history_layout.addStretch()
        self._history_panel.setWidget(self._history_content)
        self._history_panel.hide()
        surface_layout.addWidget(self._history_panel, 1)
        QWidget.setTabOrder(self._text_input, self._send_btn)
        QWidget.setTabOrder(self._send_btn, self._mute_btn)
        QWidget.setTabOrder(self._mute_btn, self._history_btn)
        QWidget.setTabOrder(self._history_btn, self._new_btn)
        QWidget.setTabOrder(self._new_btn, self._settings_btn)
        QWidget.setTabOrder(self._settings_btn, self._stop_btn)
        QWidget.setTabOrder(self._stop_btn, self._close_btn)
        self._update_mute_text()

    def _make_button(
        self,
        text: str,
        *,
        object_name: str | None = None,
        role: str | None = None,
        checkable: bool = False,
    ) -> QToolButton:
        button = QToolButton(self._surface)
        button.setText(text)
        button.setAutoRaise(True)
        button.setCheckable(checkable)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setAccessibleName(text)
        button.setToolTip(text)
        if object_name:
            button.setObjectName(object_name)
        if role:
            button.setProperty("role", role)
        return button

    def _submit_text(self) -> None:
        text = self._text_input.text().strip()
        if not text or not self._text_input.isEnabled():
            return
        self._text_input.clear()
        self.text_submitted.emit(text)

    def show_confirmation(self, question: str) -> None:
        """Replace the text input with inline controls for a destructive tool."""
        self._confirmation_visible = True
        self._text_input.hide()
        self._send_btn.hide()
        self._confirm_btn.show()
        self._deny_btn.show()
        self.set_state("confirming", title=question, hint=self._t.t("bar.confirming.hint"))
        self._confirm_btn.setFocus()

    def _answer_confirmation(self, allowed: bool) -> None:
        if not self._confirmation_visible:
            return
        self._clear_confirmation()
        self.confirmation_answered.emit(allowed)

    def _clear_confirmation(self) -> None:
        self._confirmation_visible = False
        self._confirm_btn.hide()
        self._deny_btn.hide()
        self._text_input.show()
        self._send_btn.show()

    # ----------------------------------------------------------------- state
    @property
    def state(self) -> str:
        return self._state

    def set_state(
        self,
        state: str,
        *,
        title: str | None = None,
        hint: str | None = None,
        tooltip: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        if state == "hidden":
            self.hide_bar()
            return

        if state != "confirming" and self._confirmation_visible:
            self._clear_confirmation()
        self._state = state
        self._hide_after_ms = timeout_ms
        title_key, hint_key = STATE_KEYS.get(state, STATE_KEYS["summoned"])
        if hint is None and state in ("summoned", "listening"):
            mode = self._config.ui.speech_mode
            if mode in ("toggle", "vad"):
                hint_key = f"{title_key.rsplit('.', 1)[0]}.{mode}_hint"
        self._title.setText(title or self._t.t(title_key))
        self._title.setToolTip(tooltip or title or "")
        self._hint.setText(hint or self._t.t(hint_key, hotkey=self._hotkey))
        self._orb.set_state(state)
        self._stop_btn.setVisible(state in _ACTIVE_STATES)
        self._set_input_enabled(state not in _ACTIVE_STATES)
        self._restart_hide_timer()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(muted)
        self._mute_btn.blockSignals(False)
        self._update_mute_text()

    def _on_mute_toggled(self, checked: bool) -> None:
        self._muted = checked
        self._update_mute_text()
        self.mute_toggled.emit(checked)

    def _update_mute_text(self) -> None:
        label = self._t.t("bar.mute.short")
        action = self._t.t("bar.unmute" if self._muted else "bar.mute")
        self._mute_btn.setText(label)
        self._mute_btn.setToolTip(action)
        self._mute_btn.setAccessibleName(action)

    def set_hotkey(self, hotkey: str) -> None:
        self._hotkey = format_hotkey(hotkey)

    @property
    def history_visible(self) -> bool:
        return self._history_visible

    def set_history(self, history: list[dict[str, Any]]) -> None:
        """Store the current session history and update an open panel."""
        self._history = [
            item
            for item in history
            if item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
        ]
        if self._history_visible:
            self._render_history()

    def toggle_history(self) -> None:
        if not self._config.ui.history_enabled:
            return
        self._set_history_visible(not self._history_visible)

    def clear_history(self) -> None:
        self.set_history([])
        self._set_history_visible(False)

    def _set_history_visible(self, visible: bool) -> None:
        self._history_visible = visible
        self._history_panel.setVisible(visible)
        self._history_btn.blockSignals(True)
        self._history_btn.setChecked(visible)
        self._history_btn.blockSignals(False)
        if visible:
            self._render_history()
        self.setFixedSize(
            BAR["width"],
            BAR["expanded_height"] if visible else BAR["input_height"],
        )
        if self.isVisible():
            self._position()
        self._restart_hide_timer()

    def _render_history(self) -> None:
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()

        if not self._history:
            self._add_history_label("bar.history.empty", "caption")
        else:
            for item in self._history:
                role = item["role"]
                self._add_history_label(
                    "bar.history.user" if role == "user" else "bar.history.assistant",
                    f"history-{role}",
                )
                label = QLabel(item["content"], self._history_content)
                label.setProperty("role", "history-content")
                label.setTextFormat(Qt.PlainText)
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self._history_layout.insertWidget(self._history_layout.count() - 1, label)
        QTimer.singleShot(0, lambda: self._history_panel.verticalScrollBar().setValue(0))

    def _add_history_label(self, key: str, role: str) -> None:
        label = QLabel(self._t.t(key), self._history_content)
        label.setProperty("role", role)
        self._history_layout.insertWidget(self._history_layout.count() - 1, label)

    def _set_input_enabled(self, enabled: bool) -> None:
        self._text_input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def set_reduced_motion(self, reduced: bool) -> None:
        self._orb.set_reduced_motion(reduced)

    def apply_theme(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._orb.set_tokens(tokens)

    def retranslate(self, translator: Translator) -> None:
        self._t = translator
        self._stop_btn.setText(translator.t("bar.stop"))
        self._history_btn.setText(translator.t("bar.history"))
        self._history_panel.setAccessibleName(translator.t("bar.history.panel"))
        self._text_input.setPlaceholderText(translator.t("bar.input.placeholder"))
        self._text_input.setAccessibleName(translator.t("bar.input.placeholder"))
        self._send_btn.setText(translator.t("bar.input.send"))
        self._send_btn.setToolTip(translator.t("bar.input.send"))
        self._send_btn.setAccessibleName(translator.t("bar.input.send"))
        self._confirm_btn.setText(translator.t("bar.confirming.yes"))
        self._confirm_btn.setToolTip(translator.t("bar.confirming.yes"))
        self._confirm_btn.setAccessibleName(translator.t("bar.confirming.yes"))
        self._deny_btn.setText(translator.t("bar.confirming.no"))
        self._deny_btn.setToolTip(translator.t("bar.confirming.no"))
        self._deny_btn.setAccessibleName(translator.t("bar.confirming.no"))
        self._new_btn.setText(translator.t("bar.new.short"))
        self._new_btn.setToolTip(translator.t("bar.new"))
        self._new_btn.setAccessibleName(translator.t("bar.new"))
        self._settings_btn.setText(translator.t("bar.settings"))
        self._close_btn.setToolTip(translator.t("bar.close"))
        self._close_btn.setAccessibleName(translator.t("bar.close"))
        self._update_mute_text()
        if self._history_visible:
            self._render_history()
        if self._state != "hidden":
            self.set_state(self._state)

    # ---------------------------------------------------------------- window
    def show_bar(self, state: str = "summoned", **state_kwargs: Any) -> None:
        self._hiding = False
        self.set_state(state, **state_kwargs)
        self._position()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
            self._shown_at = time.monotonic()
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        self.raise_()
        self.activateWindow()
        self._sync_focus(state)
        self._restart_hide_timer()

    def _sync_focus(self, state: str) -> None:
        """Put focus where it is useful for the current state.

        A button that kept focus from a previous session would otherwise be
        activated by the space key of the global hotkey (Ctrl+Alt+Space) and
        close the bar while a voice turn is running.
        """
        if state in _ACTIVE_STATES:
            self._surface.setFocus()
        elif state == "summoned":
            self._text_input.setFocus()

    def hide_bar(self) -> None:
        if not self.isVisible() or self._hiding:
            return
        self._hiding = True
        self._hide_timer.stop()
        if self._config.ui.reduced_motion:
            self._finish_hide()
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._hiding:
            self._finish_hide()

    def _finish_hide(self) -> None:
        self.hide()
        self._clear_confirmation()
        self._set_history_visible(False)
        self.setWindowOpacity(1.0)
        self._hiding = False
        self._state = "hidden"
        self._hide_after_ms = None
        self._orb.set_state("hidden")
        # Note: focus is re-established in show_bar/_sync_focus (a focus
        # change does not stick while the window is hidden).
        self.hidden.emit()

    def _typing_in_progress(self) -> bool:
        return self._text_input.hasFocus() or bool(self._text_input.text().strip())

    def _restart_hide_timer(self) -> None:
        if (
            self._state in _AUTO_HIDE_STATES
            and self.isVisible()
            and not self._history_visible
            and not self._typing_in_progress()
        ):
            self._hide_timer.start(self._hide_after_ms or self._config.ui.auto_hide_ms)
        else:
            self._hide_timer.stop()

    def _position(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        x = available.x() + (available.width() - self.width()) // 2
        y = available.y() + available.height() - self.height() - BAR["bottom_offset"]
        self.move(max(available.x(), x), max(available.y(), y))

    # ---------------------------------------------------------------- events
    def event(self, event) -> bool:  # noqa: N802 (Qt override)
        if (
            event.type() == QEvent.WindowDeactivate
            and self.isVisible()
            and not self._hiding
            and time.monotonic() - self._shown_at > 0.25
            and self._state in _AUTO_HIDE_STATES
        ):
            QTimer.singleShot(0, self._hide_if_inactive)
        return super().event(event)

    def _hide_if_inactive(self) -> None:
        if self.isVisible() and not self.isActiveWindow() and self._state in _AUTO_HIDE_STATES:
            self.hide_bar()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        if obj is self._text_input and event.type() == QEvent.FocusOut:
            QTimer.singleShot(0, self._restart_hide_timer)
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() == Qt.Key_Escape:
            self.hide_bar()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        event.ignore()
        self.hide_bar()
