"""Theme token and style sheet tests."""

from __future__ import annotations

from naji.ui.theme import (
    FONT_SANS_FAMILY,
    build_qss,
    get_tokens,
    load_application_fonts,
    resolve_theme,
    rgba,
)


def test_theme_tokens() -> None:
    dark = get_tokens("dark")
    light = get_tokens("light")
    assert dark["background"] == "#09090b"
    assert light["background"] == "#fafafa"
    assert dark["accent"] != light["accent"]
    assert rgba("#ffffff", 0.5) == "rgba(255, 255, 255, 128)"


def test_resolve_theme() -> None:
    assert resolve_theme("dark") == "dark"
    assert resolve_theme("light") == "light"
    assert resolve_theme("system") in ("dark", "light")


def test_qss_is_fully_resolved() -> None:
    for theme in ("dark", "light"):
        qss = build_qss(get_tokens(theme))
        assert "%(" not in qss
        assert "QFrame#NajiBarSurface" in qss
        assert "rgba(" in qss
        assert "QToolButton:focus" in qss
        assert "QComboBox:focus" in qss
        assert "border: 2px solid" in qss
    assert "#09090b" in build_qss(get_tokens("dark"))


def test_qss_pill_radii_are_qt_safe() -> None:
    from naji.ui.theme.tokens import RADIUS

    # Qt's QSS engine drops radii larger than half the widget height, which
    # renders square corners. Pill radii must stay below the control heights.
    assert RADIUS["pill_button"] <= 14
    assert RADIUS["pill_input"] <= 17
    qss = build_qss(get_tokens("dark"))
    assert "9999px" not in qss
    assert "border-radius: 13px" in qss
    assert "border-radius: 17px" in qss


def test_bundled_geist_fonts_are_registered(qapp) -> None:
    assert FONT_SANS_FAMILY == "Geist"
    families = load_application_fonts()
    assert "Geist" in families
    assert "Geist Mono" in families
