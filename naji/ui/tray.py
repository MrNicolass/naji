"""System tray icon and menu."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from naji.config import Config
from naji.i18n import Translator
from naji.platform.autostart import is_autostart_enabled
from naji.ui.theme.tokens import FONT_SANS_FAMILY

log = logging.getLogger(__name__)

_TOOLTIP_KEYS = {
    "standby": "tray.tooltip.standby",
    "summoned": "tray.tooltip.standby",
    "listening": "tray.tooltip.listening",
    "transcribing": "tray.tooltip.transcribing",
    "thinking": "tray.tooltip.thinking",
    "acting": "tray.tooltip.acting",
    "confirming": "tray.tooltip.confirming",
    "speaking": "tray.tooltip.speaking",
    "done": "tray.tooltip.done",
    "error": "tray.tooltip.error",
    "disconnected": "tray.tooltip.disconnected",
}

_DOT_KEYS = {
    "standby": "neutral_dot",
    "summoned": "neutral_dot",
    "listening": "success",
    "transcribing": "warning",
    "thinking": "warning",
    "acting": "warning",
    "confirming": "warning",
    "speaking": "accent",
    "done": "success",
    "error": "danger",
    "disconnected": "danger",
}


class NajiTray(QObject):
    """Tray icon with the few controls the user needs while Naji is hidden."""

    open_requested = Signal()
    new_requested = Signal()
    mute_toggled = Signal(bool)
    settings_requested = Signal()
    autostart_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(
        self,
        config: Config,
        translator: Translator,
        tokens: dict[str, str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._t = translator
        self._tokens = tokens
        self._state = "standby"
        self._muted = False
        self._syncing = False
        try:
            self._config.ui.start_with_windows = is_autostart_enabled()
        except Exception:
            log.debug("Could not read autostart state", exc_info=True)

        self._tray = QSystemTrayIcon(self)
        self._tray.activated.connect(self._on_activated)
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.setIcon(self._create_icon())
        self._tray.setToolTip(self._t.t("tray.tooltip.standby"))

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        self._menu.clear()

        self._action_open = QAction(self._t.t("tray.open"), self)
        self._action_open.triggered.connect(self._emit_open)
        self._menu.addAction(self._action_open)

        self._action_new = QAction(self._t.t("tray.new"), self)
        self._action_new.triggered.connect(self._emit_new)
        self._menu.addAction(self._action_new)

        self._menu.addSeparator()

        self._action_mute = QAction(self._t.t("tray.mute"), self)
        self._action_mute.setCheckable(True)
        self._action_mute.setChecked(self._muted)
        self._action_mute.toggled.connect(self._on_mute_toggled)
        self._menu.addAction(self._action_mute)

        self._action_autostart = QAction(self._t.t("tray.autostart"), self)
        self._action_autostart.setCheckable(True)
        self._action_autostart.setChecked(self._config.ui.start_with_windows)
        self._action_autostart.toggled.connect(self._on_autostart_toggled)
        self._menu.addAction(self._action_autostart)

        self._action_settings = QAction(self._t.t("tray.settings"), self)
        self._action_settings.triggered.connect(self._emit_settings)
        self._menu.addAction(self._action_settings)

        self._menu.addSeparator()

        self._action_quit = QAction(self._t.t("tray.quit"), self)
        self._action_quit.triggered.connect(self._emit_quit)
        self._menu.addAction(self._action_quit)

    def _emit_open(self, _checked: bool = False) -> None:
        self.open_requested.emit()

    def _emit_new(self, _checked: bool = False) -> None:
        self.new_requested.emit()

    def _emit_settings(self, _checked: bool = False) -> None:
        self.settings_requested.emit()

    def _emit_quit(self, _checked: bool = False) -> None:
        self.quit_requested.emit()

    def _on_mute_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        self._muted = checked
        self._action_mute.setText(self._t.t("tray.unmute" if checked else "tray.mute"))
        self.mute_toggled.emit(checked)

    def _on_autostart_toggled(self, checked: bool) -> None:
        if self._syncing:
            return
        self.autostart_toggled.emit(checked)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_requested.emit()

    # ----------------------------------------------------------------- state
    def set_state(self, state: str) -> None:
        self._state = state
        self._tray.setIcon(self._create_icon())
        self._tray.setToolTip(self._t.t(_TOOLTIP_KEYS.get(state, "tray.tooltip.standby")))

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._syncing = True
        self._action_mute.setChecked(muted)
        self._syncing = False
        self._action_mute.setText(self._t.t("tray.unmute" if muted else "tray.mute"))

    def set_autostart(self, enabled: bool) -> None:
        self._config.ui.start_with_windows = enabled
        self._syncing = True
        self._action_autostart.setChecked(enabled)
        self._syncing = False

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = tokens
        self._tray.setIcon(self._create_icon())

    def retranslate(self, translator: Translator) -> None:
        self._t = translator
        self._action_open.setText(translator.t("tray.open"))
        self._action_new.setText(translator.t("tray.new"))
        self._action_mute.setText(translator.t("tray.unmute" if self._muted else "tray.mute"))
        self._action_autostart.setText(translator.t("tray.autostart"))
        self._action_settings.setText(translator.t("tray.settings"))
        self._action_quit.setText(translator.t("tray.quit"))
        self._tray.setToolTip(translator.t(_TOOLTIP_KEYS.get(self._state, "tray.tooltip.standby")))

    # ---------------------------------------------------------------- window
    def show(self) -> None:
        if not self._config.ui.show_tray:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("System tray is not available; continuing without an icon")
            return
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information,
        msecs: int = 4000,
    ) -> None:
        self._tray.showMessage(title, message, icon, msecs)

    # ------------------------------------------------------------------ icon
    def _create_icon(self) -> QIcon:
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._tokens["accent"]))
        painter.drawRoundedRect(QRectF(6, 6, 52, 52), 15, 15)

        painter.setPen(QColor(self._tokens["on_accent"]))
        painter.setFont(QFont(FONT_SANS_FAMILY, 26, QFont.Weight.DemiBold))
        painter.drawText(QRectF(6, 4, 52, 52), Qt.AlignCenter, "N")

        dot = QColor(self._tokens[_DOT_KEYS.get(self._state, "neutral_dot")])
        painter.setPen(QPen(QColor(self._tokens["background"]), 4))
        painter.setBrush(dot)
        painter.drawEllipse(QRectF(38, 38, 20, 20))

        painter.end()
        return QIcon(pixmap)
