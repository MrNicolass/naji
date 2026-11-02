"""Platform-specific implementations."""

import sys

if sys.platform == "win32":
    from naji.platform.windows import (
        create_hidden_window,
        enable_ansi_colors,
        media_next,
        media_play_pause,
        media_previous,
        register_hotkey,
        send_media_key,
        set_process_dpi_aware,
        unregister_hotkey,
        volume_down,
        volume_mute,
        volume_up,
    )

    __all__ = [
        "create_hidden_window",
        "enable_ansi_colors",
        "media_next",
        "media_play_pause",
        "media_previous",
        "register_hotkey",
        "send_media_key",
        "set_process_dpi_aware",
        "unregister_hotkey",
        "volume_down",
        "volume_mute",
        "volume_up",
    ]
else:
    from naji.platform.linux import (
        GnomeMediaKeys,
        KDEGlobalShortcuts,
        MPRIS2Controller,
        get_default_audio_sink,
        get_desktop_environment,
        set_default_audio_sink,
    )

    __all__ = [
        "GnomeMediaKeys",
        "KDEGlobalShortcuts",
        "MPRIS2Controller",
        "get_default_audio_sink",
        "get_desktop_environment",
        "set_default_audio_sink",
    ]
