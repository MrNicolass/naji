"""Janela principal do Naji Desktop."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from naji.config import Config
from naji.ui.styles import TOKENS, get_qss, set_muted_label, set_secondary_label
from naji.ui.widgets import CDSButton, CDSCard, ChatBubble, LevelMeter, StatusBadge


class MainWindow(QMainWindow):
    """Janela principal com chat, painel lateral e system tray."""

    # Sinais para comunicação com backend
    ptt_pressed = Signal()
    ptt_released = Signal()
    send_text = Signal(str)
    toggle_mute = Signal(bool)
    cancel_response = Signal()

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._muted = False
        self._connected = False
        self._ptt_active = False
        self._setup_ui()
        self._apply_styles()
        self._setup_tray()
        self._setup_hotkeys()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Naji")
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)

        # Central widget com splitter
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- Lado esquerdo: Chat ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Header do chat
        chat_header = QWidget()
        chat_header.setFixedHeight(56)
        chat_header.setStyleSheet(f"background: {TOKENS['bg_surface']}; border-bottom: 1px solid {TOKENS['border']};")
        header_layout = QHBoxLayout(chat_header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        self._status_badges = QWidget()
        badges_layout = QHBoxLayout(self._status_badges)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(8)

        self._badge_health = StatusBadge("Health", "pending")
        self._badge_build = StatusBadge("Build", "pending")
        self._badge_model = StatusBadge("Modelo", "pending")
        self._badge_realtime = StatusBadge("Realtime", "pending")
        self._badge_tts = StatusBadge("TTS", "pending")

        for b in [self._badge_health, self._badge_build, self._badge_model, self._badge_realtime, self._badge_tts]:
            badges_layout.addWidget(b)

        header_layout.addWidget(self._status_badges)
        header_layout.addStretch()

        self._btn_settings = CDSButton("⚙", variant="ghost", size="sm")
        self._btn_settings.setFixedSize(36, 36)
        header_layout.addWidget(self._btn_settings)

        left_layout.addWidget(chat_header)

        # Lista de mensagens
        self._chat_list = QListWidget()
        self._chat_list.setStyleSheet(f"""
            QListWidget {{
                background: {TOKENS['bg_primary']};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 0;
                margin: 8px 16px;
            }}
        """)
        self._chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_layout.addWidget(self._chat_list, 1)

        # Composer (PTT + controles)
        composer = QWidget()
        composer.setFixedHeight(120)
        composer.setStyleSheet(f"background: {TOKENS['bg_surface']}; border-top: 1px solid {TOKENS['border']};")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(16, 12, 16, 12)
        composer_layout.setSpacing(8)

        # Linha 1: PTT + Level Meter
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        self._ptt_btn = CDSButton("Segure para falar", variant="primary", size="lg")
        self._ptt_btn.setMinimumWidth(180)
        self._ptt_btn.setCheckable(True)
        self._ptt_btn.pressed.connect(self._on_ptt_pressed)
        self._ptt_btn.released.connect(self._on_ptt_released)
        row1.addWidget(self._ptt_btn)

        self._level_meter = LevelMeter(style="bars")
        row1.addWidget(self._level_meter, 1)

        self._state_label = QLabel("desconectado")
        set_muted_label(self._state_label, True)
        self._state_label.setMinimumWidth(100)
        row1.addWidget(self._state_label)

        composer_layout.addLayout(row1)

        # Linha 2: Controles
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        self._vad_checkbox = QPushButton("VAD")
        self._vad_checkbox.setCheckable(True)
        self._vad_checkbox.setChecked(True)
        self._vad_checkbox.setStyleSheet(f"""
            QPushButton {{
                background: {TOKENS['bg_primary']};
                color: {TOKENS['text_secondary']};
                border: 1px solid {TOKENS['border']};
                border-radius: {TOKENS['radius_md']};
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background: {TOKENS['accent']};
                color: {TOKENS['bg_primary']};
                border-color: {TOKENS['accent']};
            }}
        """)
        row2.addWidget(self._vad_checkbox)

        self._mute_btn = CDSButton("Mudo", variant="ghost", size="sm")
        self._mute_btn.setCheckable(True)
        self._mute_btn.toggled.connect(self._on_mute_toggled)
        row2.addWidget(self._mute_btn)

        self._cancel_btn = CDSButton("Cancelar", variant="ghost", size="sm")
        self._cancel_btn.clicked.connect(self.cancel_response.emit)
        row2.addWidget(self._cancel_btn)

        row2.addStretch()

        composer_layout.addLayout(row2)
        left_layout.addWidget(composer)

        splitter.addWidget(left_widget)

        # --- Lado direito: Painel de controle ---
        right_widget = QWidget()
        right_widget.setMinimumWidth(280)
        right_widget.setMaximumWidth(360)
        right_widget.setStyleSheet(f"background: {TOKENS['bg_surface']}; border-left: 1px solid {TOKENS['border']};")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(16)

        # Card: Status de conexão
        conn_card = CDSCard()
        conn_card.layout().addWidget(QLabel("Conexão"))
        self._conn_status = QLabel("Desconectado")
        set_muted_label(self._conn_status, True)
        conn_card.layout().addWidget(self._conn_status)

        self._btn_check = CDSButton("Verificar", variant="primary")
        self._btn_check.clicked.connect(self._on_check_clicked)
        conn_card.layout().addWidget(self._btn_check)
        right_layout.addWidget(conn_card)

        # Card: Mídia
        media_card = CDSCard()
        media_card.layout().addWidget(QLabel("Controle de Mídia"))
        media_row = QHBoxLayout()
        for txt, action in [("⏮", "previous"), ("⏯", "play_pause"), ("⏭", "next")]:
            btn = CDSButton(txt, variant="secondary", size="sm")
            btn.clicked.connect(lambda _, a=action: self._on_media_action(a))
            media_row.addWidget(btn)
        media_card.layout().addLayout(media_row)
        right_layout.addWidget(media_card)

        # Card: Ferramentas rápidas
        tools_card = CDSCard()
        tools_card.layout().addWidget(QLabel("Ferramentas"))
        for name, tip in [("Clima", "weather"), ("Hora", "datetime"), ("Buscar", "web_search")]:
            btn = CDSButton(name, variant="ghost")
            btn.clicked.connect(lambda _, t=tip: self._on_tool_action(t))
            tools_card.layout().addWidget(btn)
        right_layout.addWidget(tools_card)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        # Proporções iniciais
        splitter.setSizes([700, 300])

    def _apply_styles(self) -> None:
        self.setStyleSheet(get_qss())

    def _setup_tray(self) -> None:
        from naji.ui.system_tray import SystemTray
        self._tray = SystemTray(self, self._config)
        self._tray.show_window.connect(self._show_window)
        self._tray.hide_window.connect(self.hide)
        self._tray.toggle_mute.connect(self._on_mute_toggled)
        self._tray.quit_app.connect(self._quit_app)
        self._tray.show()

    def _setup_hotkeys(self) -> None:
        from naji.ui.global_hotkey import GlobalHotkeyManager
        self._hotkeys = GlobalHotkeyManager(self._config, self)
        self._hotkeys.ptt_pressed.connect(self._on_ptt_pressed, Qt.QueuedConnection)
        self._hotkeys.ptt_released.connect(self._on_ptt_released, Qt.QueuedConnection)
        if not self._hotkeys.start():
            self._tray.showMessage(
                "Naji",
                f"Hotkey global ({self._config.ui.hotkey}) não registrada (conflito?). Use o botão PTT.",
                QSystemTrayIcon.Warning,
            )

    # --- Event handlers ---
    def _on_ptt_pressed(self) -> None:
        if self._ptt_active:
            return
        self._ptt_active = True
        self._ptt_btn.setChecked(True)
        self._ptt_btn.setText("Gravando...")
        self.ptt_pressed.emit()

    def _on_ptt_released(self) -> None:
        if not self._ptt_active:
            return
        self._ptt_active = False
        self._ptt_btn.setChecked(False)
        self._ptt_btn.setText("Segure para falar")
        self.ptt_released.emit()

    def _on_mute_toggled(self, checked: bool) -> None:
        if self._mute_btn.isChecked() == checked:
            return
        self._mute_btn.setChecked(checked)
        self._muted = checked
        self._mute_btn.setText("Ativo" if checked else "Mudo")
        self._tray.setMuted(checked)
        self.toggle_mute.emit(checked)

    def _show_window(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self) -> None:
        self._hotkeys.stop()
        QApplication.quit()

    def _on_check_clicked(self) -> None:
        self._btn_check.setEnabled(False)
        self._btn_check.setText("Verificando...")
        # TODO: chamar preflight
        QTimer.singleShot(2000, lambda: self._btn_check.setEnabled(True))
        QTimer.singleShot(2000, lambda: self._btn_check.setText("Verificar"))

    def _on_media_action(self, action: str) -> None:
        # TODO: chamar tool media_control
        pass

    def _on_tool_action(self, tool: str) -> None:
        # TODO: chamar tool correspondente
        pass

    # --- Public API ---
    def addUserMessage(self, text: str) -> None:
        bubble = ChatBubble(text, is_user=True)
        item = QListWidgetItem()
        item.setSizeHint(bubble.sizeHint())
        self._chat_list.addItem(item)
        self._chat_list.setItemWidget(item, bubble)
        self._chat_list.scrollToBottom()

    def addAssistantMessage(self, text: str, has_audio: bool = False) -> ChatBubble:
        bubble = ChatBubble(text, is_user=False, has_audio=has_audio)
        item = QListWidgetItem()
        item.setSizeHint(bubble.sizeHint())
        self._chat_list.addItem(item)
        self._chat_list.setItemWidget(item, bubble)
        self._chat_list.scrollToBottom()
        return bubble

    def updateAssistantMessage(self, bubble: ChatBubble, delta: str) -> None:
        bubble.appendText(delta)
        self._chat_list.scrollToBottom()

    def setLevel(self, level: float) -> None:
        self._level_meter.setLevel(level)

    def setConnectionStatus(self, connected: bool, details: str = "") -> None:
        self._connected = connected
        if connected:
            self._conn_status.setText("Conectado")
            set_secondary_label(self._conn_status, False)
            self._state_label.setText("conectado")
        else:
            self._conn_status.setText("Desconectado")
            set_muted_label(self._conn_status, True)
            self._state_label.setText("desconectado")

    def updateBadges(self, health: str, build: str, model: str, realtime: str, tts: str) -> None:
        self._badge_health.setStatus("ok" if health == "ok" else "error", "Health")
        self._badge_build.setStatus("ok" if build == "ok" else "warning", "Build")
        self._badge_model.setStatus("ok" if model == "ok" else "warning", "Modelo")
        self._badge_realtime.setStatus("ok" if realtime == "ok" else "error", "Realtime")
        self._badge_tts.setStatus("ok" if tts == "ok" else "error", "TTS")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._tray.setVisible(True)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._tray.setVisible(False)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._config.ui.show_tray:
            event.ignore()
            self.hide()
        else:
            self._hotkeys.stop()
            event.accept()
