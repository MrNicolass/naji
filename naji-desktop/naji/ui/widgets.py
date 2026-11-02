"""Componentes CDS (PySide6 widgets customizados)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from naji.ui.styles import (
    TOKENS,
    set_card_frame,
    set_danger_button,
    set_ghost_button,
    set_primary_button,
)


class CDSButton(QPushButton):
    """Botão CDS: primary, secondary, ghost, danger."""

    def __init__(
        self,
        text: str = "",
        *,
        variant: str = "secondary",  # primary, secondary, ghost, danger
        size: str = "md",            # sm, md, lg
        parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._size = size
        self._apply_variant()
        self._apply_size()

    def _apply_variant(self) -> None:
        set_primary_button(self, self._variant == "primary")
        set_ghost_button(self, self._variant == "ghost")
        set_danger_button(self, self._variant == "danger")

    def _apply_size(self) -> None:
        sizes = {
            "sm": (8, 12, 11),
            "md": (10, 16, 13),
            "lg": (14, 24, 15),
        }
        py, px, fs = sizes.get(self._size, sizes["md"])
        self.setStyleSheet(f"""
            QPushButton {{
                padding: {py}px {px}px;
                font-size: {fs}px;
            }}
        """)


class CDSCard(QFrame):
    """Card CDS com raio 12px, borda sutil."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        set_card_frame(self, True)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(16, 16, 16, 16)
        self.layout().setSpacing(12)


class CDSInput(QLineEdit):
    """Input com label flutuante (placeholder)."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)


class CDSTextArea(QTextEdit):
    """TextArea CDS."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setLineWrapMode(QTextEdit.WidgetWidth)


class ChatBubble(QWidget):
    """Bolha de chat (user/assistant) com texto incremental e botão salvar WAV."""

    def __init__(
        self,
        text: str = "",
        *,
        is_user: bool = False,
        has_audio: bool = False,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._is_user = is_user
        self._has_audio = has_audio
        self._full_text = text
        self._displayed_text = ""
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate_text)
        self._char_index = 0
        self._chars_per_tick = 2

        self._setup_ui()
        self.setText(text)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        if self._is_user:
            layout.addStretch()

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._text_label.setStyleSheet(f"""
            QLabel {{
                background-color: {TOKENS['accent'] if self._is_user else TOKENS['bg_surface']};
                color: {TOKENS['bg_primary'] if self._is_user else TOKENS['text_primary']};
                border-radius: {TOKENS['radius_lg']};
                padding: 10px 14px;
            }}
        """)
        layout.addWidget(self._text_label)

        if self._has_audio and not self._is_user:
            self._save_btn = CDSButton("💾", variant="ghost", size="sm")
            self._save_btn.setFixedSize(28, 28)
            self._save_btn.setToolTip("Salvar áudio")
            layout.addWidget(self._save_btn)

        if not self._is_user:
            layout.addStretch()

    def setText(self, text: str, animate: bool = True) -> None:
        self._full_text = text
        if animate and not self._is_user:
            self._displayed_text = ""
            self._char_index = 0
            self._text_label.setText("")
            self._animation_timer.start(30)
        else:
            self._displayed_text = text
            self._text_label.setText(text)

    def _animate_text(self) -> None:
        if self._char_index < len(self._full_text):
            end = min(self._char_index + self._chars_per_tick, len(self._full_text))
            self._displayed_text = self._full_text[:end]
            self._text_label.setText(self._displayed_text)
            self._char_index = end
        else:
            self._animation_timer.stop()

    def appendText(self, delta: str) -> None:
        """Adiciona texto incrementalmente (streaming)."""
        self._full_text += delta
        if not self._animation_timer.isActive():
            self._displayed_text += delta
            self._text_label.setText(self._displayed_text)

    def setAudioPath(self, path: str) -> None:
        self._has_audio = True
        # TODO: conectar save_btn


class LevelMeter(QWidget):
    """Medidor de nível de áudio (waveform/barra) 60fps."""

    def __init__(self, parent: QWidget | None = None, style: str = "bars") -> None:
        super().__init__(parent)
        self._style = style  # "bars" ou "wave"
        self._level = 0.0
        self._peak = 0.0
        self._history: list[float] = []
        self._max_history = 80

        self.setFixedHeight(44)
        self.setMinimumWidth(200)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(16)  # ~60fps

    def setLevel(self, level: float) -> None:
        """level: 0.0 a 1.0 (RMS normalizado)."""
        self._level = max(0.0, min(1.0, level))
        self._peak = max(self._peak, self._level)
        self._history.append(self._level)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        self.update()

    def _decay(self) -> None:
        self._peak = max(0.0, self._peak * 0.95)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h // 2

        if self._style == "bars":
            self._paint_bars(painter, w, h, mid_y)
        else:
            self._paint_wave(painter, w, h, mid_y)

    def _paint_bars(self, painter: QPainter, w: int, h: int, mid_y: int) -> None:
        bar_count = 30
        bar_width = w // bar_count
        gap = 2

        for i, level in enumerate(self._history):
            x = i * (bar_width + gap)
            bar_h = int(level * (h * 0.8))
            y = mid_y - bar_h // 2

            color = QColor(TOKENS['accent'])
            color.setAlpha(int(180 * (i / len(self._history))))
            painter.fillRect(x, y, bar_width, bar_h, color)

        # Peak indicator
        peak_x = int(self._peak * w)
        painter.setPen(QPen(QColor(TOKENS['warning']), 2))
        painter.drawLine(peak_x, 0, peak_x, h)

    def _paint_wave(self, painter: QPainter, w: int, h: int, mid_y: int) -> None:
        if len(self._history) < 2:
            return

        pen = QPen(QColor(TOKENS['accent']), 2)
        painter.setPen(pen)

        path_points = []
        for i, level in enumerate(self._history):
            x = int(i * w / len(self._history))
            y = mid_y - int(level * mid_y * 0.8)
            path_points.append(QPoint(x, y))

        for i in range(len(path_points) - 1):
            painter.drawLine(path_points[i], path_points[i + 1])


class StatusBadge(QLabel):
    """Badge de status (Health, Build, Realtime, TTS)."""

    def __init__(self, text: str = "", status: str = "pending", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._status = status
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(24)
        self.setMinimumWidth(70)
        self._update_style()

    def setStatus(self, status: str, text: str | None = None) -> None:
        self._status = status
        if text:
            self.setText(text)
        self._update_style()

    def _update_style(self) -> None:
        colors = {
            "ok": (TOKENS['success'], TOKENS['bg_primary']),
            "warning": (TOKENS['warning'], TOKENS['bg_primary']),
            "error": (TOKENS['danger'], TOKENS['bg_primary']),
            "pending": (TOKENS['text_muted'], TOKENS['bg_surface']),
            "connecting": (TOKENS['accent'], TOKENS['bg_primary']),
        }
        bg, fg = colors.get(self._status, colors["pending"])
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border-radius: 12px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)


class CDSDialog(QFrame):
    """Modal/Dialog estilo CDS (overlay)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        set_card_frame(self, True)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.ApplicationModal)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(f"font-size: 18px; font-weight: 600; color: {TOKENS['text_primary']};")
            layout.addWidget(lbl)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(12)
        layout.addLayout(self._content_layout)

    def addWidget(self, widget: QWidget) -> None:
        self._content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self._content_layout.addLayout(layout)
