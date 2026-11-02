"""Build the application style sheet from design tokens."""

from __future__ import annotations

from naji.ui.theme.tokens import BORDER, FONT_SANS_STACK, FONT_SIZE, RADIUS, SPACE

_BAR_SURFACE = """
QFrame#NajiBarSurface {
    background-color: %(background)s;
    border: 1px solid %(border)s;
    border-radius: %(radius_lg)s;
}
"""

_RULES = """
QWidget {
    color: %(text_primary)s;
    font-family: %(font_sans)s;
    font-size: %(fs_body_sm)s;
    selection-background-color: %(accent_soft)s;
    selection-color: %(text_primary)s;
}

QLabel[role="title"] {
    color: %(text_primary)s;
    font-size: %(fs_body)s;
    font-weight: 600;
}
QLabel[role="secondary"] {
    color: %(text_muted)s;
    font-size: %(fs_body_sm)s;
}
QLabel[role="caption"] {
    color: %(text_subtle)s;
    font-size: %(fs_caption)s;
}
QLabel[role="history-user"] {
    color: %(accent)s;
    font-size: %(fs_caption)s;
    font-weight: 600;
}
QLabel[role="history-assistant"] {
    color: %(text_secondary)s;
    font-size: %(fs_caption)s;
    font-weight: 600;
}
QLabel[role="history-content"] {
    color: %(text_primary)s;
    font-size: %(fs_body_sm)s;
}
QLabel[role="danger"] {
    color: %(danger)s;
}

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: %(radius_pill_button)s;
    padding: %(space_xs)s %(space_sm)s;
    color: %(text_muted)s;
    font-size: %(fs_body_sm)s;
}
QToolButton:hover {
    background: %(surface_muted)s;
    color: %(text_primary)s;
}
QToolButton:pressed {
    background: %(accent_soft)s;
    color: %(accent)s;
}
QToolButton:checked {
    background: %(accent_soft)s;
    color: %(accent)s;
    border-color: %(border)s;
}
QToolButton:focus {
    border: %(border_focus)s solid %(focus)s;
}
QToolButton[role="accent"] {
    background: %(accent_soft)s;
    color: %(accent)s;
    border-color: %(border)s;
}
QToolButton[role="danger"] {
    color: %(danger)s;
}
QToolButton[role="danger"]:hover {
    background: %(surface_muted)s;
    color: %(danger)s;
}
QToolButton#NajiClose {
    font-size: %(fs_heading)s;
    padding: 0;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}

QLineEdit {
    background: %(surface_muted)s;
    border: 1px solid %(border)s;
    border-radius: %(radius_pill_input)s;
    padding: %(space_sm)s %(space_lg)s;
    color: %(text_primary)s;
}
QLineEdit:focus {
    border: %(border_focus)s solid %(focus)s;
    background: %(surface)s;
}
QComboBox:focus,
QSpinBox:focus {
    border: %(border_focus)s solid %(focus)s;
}

QMenu {
    background: %(background)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: %(radius_md)s;
    padding: %(space_sm)s;
}
QMenu::item {
    padding: %(space_sm)s %(space_lg)s;
    border-radius: %(radius_sm)s;
}
QMenu::item:selected {
    background: %(surface_muted)s;
    color: %(text_primary)s;
}
QMenu::item:disabled {
    color: %(text_faint)s;
}
QMenu::separator {
    height: 1px;
    background: %(border)s;
    margin: %(space_xs)s %(space_sm)s;
}

QToolTip {
    background: %(background)s;
    color: %(text_primary)s;
    border: 1px solid %(border)s;
    border-radius: %(radius_sm)s;
    padding: %(space_xs)s %(space_sm)s;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: %(surface_strong)s;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: %(accent_soft)s;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


def build_qss(tokens: dict[str, str]) -> str:
    """Return a complete Qt style sheet for the given token set."""
    values: dict[str, str] = dict(tokens)
    values.update(
        {
            "font_sans": FONT_SANS_STACK,
            "fs_caption": f"{FONT_SIZE['caption']}px",
            "fs_body_sm": f"{FONT_SIZE['body_sm']}px",
            "fs_body": f"{FONT_SIZE['body']}px",
            "fs_heading": f"{FONT_SIZE['heading']}px",
            "border_focus": f"{BORDER['focus']}px",
            "radius_sm": f"{RADIUS['sm']}px",
            "radius_md": f"{RADIUS['md']}px",
            "radius_lg": f"{RADIUS['lg']}px",
            "radius_pill_button": f"{RADIUS['pill_button']}px",
            "radius_pill_input": f"{RADIUS['pill_input']}px",
            "space_xs": f"{SPACE['xs']}px",
            "space_sm": f"{SPACE['sm']}px",
            "space_lg": f"{SPACE['lg']}px",
        }
    )
    return (_BAR_SURFACE + _RULES) % values
