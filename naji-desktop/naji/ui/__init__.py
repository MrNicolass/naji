"""UI modules: styles, widgets, main_window, system_tray."""

from naji.ui.global_hotkey import GlobalHotkeyManager
from naji.ui.main_window import MainWindow
from naji.ui.styles import (
    TOKENS,
    get_qss,
    set_card_frame,
    set_danger_button,
    set_ghost_button,
    set_primary_button,
)
from naji.ui.system_tray import SystemTray
from naji.ui.widgets import (
    CDSButton,
    CDSCard,
    CDSInput,
    CDSTextArea,
    ChatBubble,
    LevelMeter,
    StatusBadge,
)

__all__ = [
    "get_qss",
    "TOKENS",
    "set_primary_button",
    "set_ghost_button",
    "set_danger_button",
    "set_card_frame",
    "CDSButton",
    "CDSCard",
    "ChatBubble",
    "LevelMeter",
    "StatusBadge",
    "CDSInput",
    "CDSTextArea",
    "MainWindow",
    "SystemTray",
    "GlobalHotkeyManager",
]
