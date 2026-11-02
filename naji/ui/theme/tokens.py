"""Design tokens derived from the Conte Design System (CDS).

Semantic names only: components must not hardcode colors, radii or spacing.
Values follow the CDS dark/light palettes; translucent surfaces use integer
alpha (0-255) because that is what Qt style sheets accept.
"""

from __future__ import annotations

from typing import Literal

Theme = Literal["dark", "light"]

FONT_SANS_FAMILY = "Geist"
FONT_SANS_STACK = '"Geist", "Segoe UI", "Ubuntu", sans-serif'
FONT_MONO_STACK = '"Geist Mono", "Cascadia Mono", "Consolas", monospace'

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
# Qt's QSS engine drops border-radius values larger than half the widget
# height (they render as square corners), so "pill" radii are expressed as
# concrete pixel values per control height: buttons are ~27px tall, the text
# input ~34px.
RADIUS = {"sm": 8, "md": 16, "lg": 24, "pill_button": 13, "pill_input": 17}
BORDER = {"default": 1, "focus": 2}
FONT_SIZE = {"caption": 12, "body_sm": 14, "body": 16, "heading": 18, "display": 32}
MOTION = {"fast": 150, "base": 300}
BAR = {
    "width": 744,
    "collapsed_height": 96,
    "input_height": 152,
    "expanded_height": 504,
    "bottom_offset": 12,
}


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(color: str, alpha: float) -> str:
    """Return a Qt-compatible ``rgba(r, g, b, a)`` string."""
    r, g, b = hex_to_rgb(color)
    return f"rgba({r}, {g}, {b}, {max(0, min(255, round(alpha * 255)))})"


DARK: dict[str, str] = {
    "background": "#09090b",
    "foreground": "#f4f4f5",
    "surface": rgba("#ffffff", 0.06),
    "surface_muted": rgba("#ffffff", 0.10),
    "surface_strong": rgba("#ffffff", 0.14),
    "border": rgba("#ffffff", 0.10),
    "border_strong": rgba("#ffffff", 0.18),
    "accent": "#a78bfa",
    "accent_hover": "#c4b5fd",
    "accent_soft": rgba("#8b5cf6", 0.22),
    "focus": "#a78bfa",
    "text_primary": "#f4f4f5",
    "text_secondary": rgba("#f4f4f5", 0.80),
    "text_muted": rgba("#f4f4f5", 0.70),
    "text_subtle": rgba("#f4f4f5", 0.60),
    "text_faint": rgba("#f4f4f5", 0.50),
    "success": "#34d399",
    "warning": "#fbbf24",
    "danger": "#f87171",
    "neutral_dot": "#a1a1aa",
    "gradient_start": "#6366f1",
    "gradient_mid": "#8b5cf6",
    "gradient_end": "#d946ef",
    "on_accent": "#ffffff",
}

LIGHT: dict[str, str] = {
    "background": "#fafafa",
    "foreground": "#18181b",
    "surface": "#ffffff",
    "surface_muted": rgba("#000000", 0.05),
    "surface_strong": rgba("#000000", 0.09),
    "border": rgba("#000000", 0.10),
    "border_strong": rgba("#000000", 0.18),
    "accent": "#7c3aed",
    "accent_hover": "#8b5cf6",
    "accent_soft": rgba("#8b5cf6", 0.14),
    "focus": "#8b5cf6",
    "text_primary": "#18181b",
    "text_secondary": rgba("#18181b", 0.80),
    "text_muted": rgba("#18181b", 0.70),
    "text_subtle": rgba("#18181b", 0.60),
    "text_faint": rgba("#18181b", 0.50),
    "success": "#059669",
    "warning": "#d97706",
    "danger": "#dc2626",
    "neutral_dot": "#71717a",
    "gradient_start": "#6366f1",
    "gradient_mid": "#8b5cf6",
    "gradient_end": "#d946ef",
    "on_accent": "#ffffff",
}

_TOKENS: dict[Theme, dict[str, str]] = {"dark": DARK, "light": LIGHT}


def resolve_theme(theme: str) -> Theme:
    """Resolve ``system`` using the current Qt color scheme (fallback: dark)."""
    if theme in ("dark", "light"):
        return theme  # type: ignore[return-value]
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.instance() is None:
            return "dark"
        scheme = QGuiApplication.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except Exception:
        return "dark"


def get_tokens(theme: str = "dark") -> dict[str, str]:
    return dict(_TOKENS[resolve_theme(theme)])
