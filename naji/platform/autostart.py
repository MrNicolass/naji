"""Start Naji with the operating system."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Naji"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
LINUX_DESKTOP = Path.home() / ".config" / "autostart" / "naji.desktop"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --minimized'
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        executable = pythonw
    return f'"{executable}" -m naji --minimized'


def autostart_supported() -> bool:
    return os.name == "nt" or sys.platform.startswith("linux")


def is_autostart_enabled() -> bool:
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            return False
        except OSError:
            return False
        return True
    if sys.platform.startswith("linux"):
        return LINUX_DESKTOP.exists()
    return False


def set_autostart(enabled: bool) -> None:
    """Enable or disable autostart. Raises OSError if the platform fails."""
    if os.name == "nt":
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return

    if sys.platform.startswith("linux"):
        if enabled:
            LINUX_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
            LINUX_DESKTOP.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Naji\n"
                "Comment=Assistente de voz\n"
                f"Exec={_launch_command()}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        elif LINUX_DESKTOP.exists():
            LINUX_DESKTOP.unlink()
        return

    raise OSError("autostart is not supported on this platform")
