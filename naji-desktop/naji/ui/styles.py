"""QSS gerado a partir dos tokens do Conte Design System (CDS)."""

from __future__ import annotations

# Tokens CDS
TOKENS = {
    # Cores
    "bg_primary": "#0a0a0a",      # Fundo principal
    "bg_surface": "#18181b",      # Superfície (cards, painéis)
    "bg_hover": "#27272a",        # Hover em superfícies
    "border": "#27272a",          # Bordas
    "border_focus": "#8b5cf6",    # Border focus (violeta)
    "text_primary": "#f4f4f5",    # Texto principal
    "text_secondary": "#a1a1aa",  # Texto secundário
    "text_muted": "#71717a",      # Texto muted
    "accent": "#8b5cf6",          # Acento violeta
    "accent_hover": "#a78bfa",    # Acento hover
    "accent_pressed": "#7c3aed",  # Acento pressed
    "danger": "#ef4444",          # Perigo/erro
    "danger_hover": "#f87171",
    "success": "#22c55e",         # Sucesso
    "warning": "#f59e0b",         # Aviso
    # Raio
    "radius_sm": "6px",
    "radius_md": "8px",
    "radius_lg": "12px",
    # Sombra
    "shadow": "0 4px 12px rgba(0, 0, 0, 0.4)",
    # Espaçamento
    "space_xs": "4px",
    "space_sm": "8px",
    "space_md": "12px",
    "space_lg": "16px",
    "space_xl": "24px",
    # Transição
    "transition": "150ms ease",
}

# QSS Base
BASE_QSS = f"""
/* ===== BASE ===== */
QWidget {{
    background-color: {TOKENS['bg_primary']};
    color: {TOKENS['text_primary']};
    font-family: "Inter", "Segoe UI", "Ubuntu", sans-serif;
    font-size: 13px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: {TOKENS['bg_surface']};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {TOKENS['border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TOKENS['bg_hover']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {TOKENS['bg_surface']};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {TOKENS['border']};
    border-radius: 4px;
    min-width: 30px;
}}

/* ===== BUTTONS ===== */
QPushButton {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_primary']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    padding: {TOKENS['space_sm']} {TOKENS['space_md']};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {TOKENS['bg_hover']};
    border-color: {TOKENS['border_focus']};
}}
QPushButton:pressed {{
    background-color: {TOKENS['accent_pressed']};
    border-color: {TOKENS['accent']};
}}
QPushButton:disabled {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_muted']};
    border-color: {TOKENS['border']};
}}
QPushButton:focus {{
    outline: none;
    border: 2px solid {TOKENS['border_focus']};
}}

/* Primary */
QPushButton[primary="true"] {{
    background-color: {TOKENS['accent']};
    border-color: {TOKENS['accent']};
    color: {TOKENS['bg_primary']};
}}
QPushButton[primary="true"]:hover {{
    background-color: {TOKENS['accent_hover']};
    border-color: {TOKENS['accent_hover']};
}}
QPushButton[primary="true"]:pressed {{
    background-color: {TOKENS['accent_pressed']};
}}

/* Ghost */
QPushButton[ghost="true"] {{
    background-color: transparent;
    border-color: transparent;
    color: {TOKENS['text_secondary']};
}}
QPushButton[ghost="true"]:hover {{
    background-color: {TOKENS['bg_hover']};
    color: {TOKENS['text_primary']};
}}

/* Danger */
QPushButton[danger="true"] {{
    background-color: {TOKENS['danger']};
    border-color: {TOKENS['danger']};
    color: white;
}}
QPushButton[danger="true"]:hover {{
    background-color: {TOKENS['danger_hover']};
}}

/* ===== INPUTS ===== */
QLineEdit, QTextEdit {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_primary']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    padding: {TOKENS['space_sm']} {TOKENS['space_md']};
    selection-background-color: {TOKENS['accent']};
}}
QLineEdit:hover, QTextEdit:hover {{
    border-color: {TOKENS['border_focus']};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid {TOKENS['border_focus']};
}}
QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {TOKENS['bg_primary']};
    color: {TOKENS['text_muted']};
    border-color: {TOKENS['border']};
}}

/* ===== COMBOBOX ===== */
QComboBox {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_primary']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    padding: {TOKENS['space_sm']} {TOKENS['space_md']};
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {TOKENS['border_focus']};
}}
QComboBox:focus {{
    border: 2px solid {TOKENS['border_focus']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {TOKENS['text_secondary']};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_primary']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    selection-background-color: {TOKENS['accent']};
    padding: {TOKENS['space_xs']};
}}

/* ===== SLIDER ===== */
QSlider::groove:horizontal {{
    height: 4px;
    background: {TOKENS['border']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: {TOKENS['accent']};
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {TOKENS['accent_hover']};
}}

/* ===== CHECKBOX / RADIO ===== */
QCheckBox, QRadioButton {{
    spacing: {TOKENS['space_sm']};
    color: {TOKENS['text_primary']};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {TOKENS['radius_sm']};
    border: 1px solid {TOKENS['border']};
    background: {TOKENS['bg_surface']};
}}
QCheckBox::indicator:checked {{
    background: {TOKENS['accent']};
    border-color: {TOKENS['accent']};
    image: url(:/icons/check.svg);
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QRadioButton::indicator:checked {{
    background: {TOKENS['accent']};
    border-color: {TOKENS['accent']};
}}

/* ===== LABEL ===== */
QLabel {{
    color: {TOKENS['text_primary']};
}}
QLabel[secondary="true"] {{
    color: {TOKENS['text_secondary']};
}}
QLabel[muted="true"] {{
    color: {TOKENS['text_muted']};
}}

/* ===== FRAME / CARD ===== */
QFrame[card="true"] {{
    background-color: {TOKENS['bg_surface']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_lg']};
}}

/* ===== SPLITTER ===== */
QSplitter::handle {{
    background: {TOKENS['border']};
    width: 1px;
}}
QSplitter::handle:hover {{
    background: {TOKENS['border_focus']};
}}

/* ===== LISTVIEW / TREEVIEW ===== */
QListView, QTreeView {{
    background-color: {TOKENS['bg_primary']};
    border: none;
    outline: none;
}}
QListView::item, QTreeView::item {{
    padding: {TOKENS['space_sm']} {TOKENS['space_md']};
    border-radius: {TOKENS['radius_md']};
}}
QListView::item:selected, QTreeView::item:selected {{
    background-color: {TOKENS['accent']};
    color: {TOKENS['bg_primary']};
}}
QListView::item:hover, QTreeView::item:hover {{
    background-color: {TOKENS['bg_hover']};
}}

/* ===== TOOLTIP ===== */
QToolTip {{
    background-color: {TOKENS['bg_surface']};
    color: {TOKENS['text_primary']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    padding: {TOKENS['space_sm']} {TOKENS['space_md']};
}}

/* ===== PROGRESS BAR ===== */
QProgressBar {{
    background-color: {TOKENS['bg_surface']};
    border: 1px solid {TOKENS['border']};
    border-radius: {TOKENS['radius_md']};
    text-align: center;
    color: {TOKENS['text_primary']};
}}
QProgressBar::chunk {{
    background-color: {TOKENS['accent']};
    border-radius: {TOKENS['radius_md']};
}}
"""

# Helpers para aplicar propriedades customizadas
def set_primary_button(btn, primary: bool = True) -> None:
    btn.setProperty("primary", primary)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


def set_ghost_button(btn, ghost: bool = True) -> None:
    btn.setProperty("ghost", ghost)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


def set_danger_button(btn, danger: bool = True) -> None:
    btn.setProperty("danger", danger)
    btn.style().unpolish(btn)
    btn.style().polish(btn)


def set_card_frame(frame, card: bool = True) -> None:
    frame.setProperty("card", card)
    frame.style().unpolish(frame)
    frame.style().polish(frame)


def set_secondary_label(label, secondary: bool = True) -> None:
    label.setProperty("secondary", secondary)
    label.style().unpolish(label)
    label.style().polish(label)


def set_muted_label(label, muted: bool = True) -> None:
    label.setProperty("muted", muted)
    label.style().unpolish(label)
    label.style().polish(label)


def get_qss() -> str:
    """Retorna QSS completo."""
    return BASE_QSS
