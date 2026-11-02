"""System Tray icon com menu (CDS)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from naji.config import Config


class SystemTray(QObject):
    """Gerencia ícone na bandeja do sistema."""

    show_window = Signal()
    hide_window = Signal()
    toggle_mute = Signal(bool)
    quit_app = Signal()

    def __init__(self, parent: QObject | None, config: Config) -> None:
        super().__init__(parent)
        self._config = config
        self._window_visible = True

        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(self._create_icon())
        self._tray.setToolTip("Naji - Assistente de voz")
        self._tray.activated.connect(self._on_activated)

        self._menu = QMenu()
        self._setup_menu()
        self._tray.setContextMenu(self._menu)

    def _create_icon(self) -> QIcon:
        """Cria ícone simples programaticamente (quadrado CDS + N)."""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#8b5cf6"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 24, 24, 6, 6)
        painter.setPen(QColor("#f4f4f5"))
        painter.setFont(QFont("Segoe UI", 13, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "N")
        painter.end()
        return QIcon(pixmap)

    def _setup_menu(self) -> None:
        self._action_show = QAction("Mostrar", self)
        self._action_show.triggered.connect(self.show_window.emit)
        self._menu.addAction(self._action_show)

        self._action_hide = QAction("Ocultar", self)
        self._action_hide.triggered.connect(self.hide_window.emit)
        self._menu.addAction(self._action_hide)

        self._menu.addSeparator()

        self._action_mute = QAction("Silenciar", self)
        self._action_mute.setCheckable(True)
        self._action_mute.toggled.connect(self.toggle_mute.emit)
        self._menu.addAction(self._action_mute)

        self._menu.addSeparator()

        self._action_quit = QAction("Sair", self)
        self._action_quit.triggered.connect(self.quit_app.emit)
        self._menu.addAction(self._action_quit)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self._window_visible:
                self.hide_window.emit()
            else:
                self.show_window.emit()

    def show(self) -> None:
        if self._config.ui.show_tray:
            self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def setVisible(self, visible: bool) -> None:
        """Sincroniza o menu com a visibilidade da janela principal."""
        self._window_visible = visible
        self._action_show.setEnabled(not visible)
        self._action_hide.setEnabled(visible)

    def setMuted(self, muted: bool) -> None:
        self._action_mute.setChecked(muted)
        self._action_mute.setText("Ativar som" if muted else "Silenciar")

    def showMessage(self, title: str, message: str, icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information) -> None:
        self._tray.showMessage(title, message, icon, 3000)
