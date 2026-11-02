"""Utilitários específicos do Linux (MPRIS2, D-Bus, etc.)."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    raise ImportError("Este módulo é apenas para Linux")

try:
    from dbus_next.aio import MessageBus
    from dbus_next.constants import BusType
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


class MPRIS2Controller:
    """Controla players MPRIS2 via D-Bus (session bus)."""

    PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
    COMMON_PLAYERS = [
        "org.mpris.MediaPlayer2.spotify",
        "org.mpris.MediaPlayer2.firefox",
        "org.mpris.MediaPlayer2.chrome",
        "org.mpris.MediaPlayer2.chromium",
        "org.mpris.MediaPlayer2.vlc",
        "org.mpris.MediaPlayer2.mpv",
        "org.mpris.MediaPlayer2.rhythmbox",
        "org.mpris.MediaPlayer2.clementine",
    ]

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._player_proxy = None
        self._player_iface = None
        self._current_player = ""

    async def connect(self) -> bool:
        """Conecta ao session bus e encontra player ativo."""
        if not DBUS_AVAILABLE:
            return False

        try:
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

            # Tenta players conhecidos
            for player in self.COMMON_PLAYERS:
                try:
                    introspection = await self._bus.introspect(player, "/org/mpris/MediaPlayer2")
                    obj = self._bus.get_proxy_object(player, "/org/mpris/MediaPlayer2", introspection)
                    self._player_iface = obj.get_interface(self.PLAYER_INTERFACE)
                    self._current_player = player
                    return True
                except Exception:
                    continue

            # Fallback: lista todos os nomes no bus que parecem players
            names = await self._bus.list_names()
            for name in names:
                if "mpris" in name.lower() and "mediaplayer2" in name.lower():
                    try:
                        introspection = await self._bus.introspect(name, "/org/mpris/MediaPlayer2")
                        obj = self._bus.get_proxy_object(name, "/org/mpris/MediaPlayer2", introspection)
                        self._player_iface = obj.get_interface(self.PLAYER_INTERFACE)
                        self._current_player = name
                        return True
                    except Exception:
                        continue

            return False

        except Exception:
            return False

    async def play_pause(self) -> bool:
        if not self._player_iface:
            return False
        try:
            await self._player_iface.call_play_pause()
            return True
        except Exception:
            return False

    async def next(self) -> bool:
        if not self._player_iface:
            return False
        try:
            await self._player_iface.call_next()
            return True
        except Exception:
            return False

    async def previous(self) -> bool:
        if not self._player_iface:
            return False
        try:
            await self._player_iface.call_previous()
            return True
        except Exception:
            return False

    async def get_playback_status(self) -> str:
        if not self._player_iface:
            return "Unknown"
        try:
            props_iface = self._player_iface._proxy.get_interface("org.freedesktop.DBus.Properties")
            status = await props_iface.call_get(self.PLAYER_INTERFACE, "PlaybackStatus")
            return str(status.value)
        except Exception:
            return "Unknown"

    async def get_metadata(self) -> dict:
        if not self._player_iface:
            return {}
        try:
            props_iface = self._player_iface._proxy.get_interface("org.freedesktop.DBus.Properties")
            metadata = await props_iface.call_get(self.PLAYER_INTERFACE, "Metadata")
            result = {}
            for k, v in metadata.value.items():
                if hasattr(v, 'value'):
                    result[k] = v.value
                else:
                    result[k] = v
            return result
        except Exception:
            return {}

    @property
    def current_player(self) -> str:
        return self._current_player


class GnomeMediaKeys:
    """Integração com GNOME Media Keys (org.gnome.SettingsDaemon.MediaKeys)."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None
        self._media_keys_iface = None

    async def connect(self) -> bool:
        if not DBUS_AVAILABLE:
            return False
        try:
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
            introspection = await self._bus.introspect(
                "org.gnome.SettingsDaemon.MediaKeys",
                "/org/gnome/SettingsDaemon/MediaKeys"
            )
            obj = self._bus.get_proxy_object(
                "org.gnome.SettingsDaemon.MediaKeys",
                "/org/gnome/SettingsDaemon/MediaKeys",
                introspection
            )
            self._media_keys_iface = obj.get_interface("org.gnome.SettingsDaemon.MediaKeys")
            return True
        except Exception:
            return False

    async def grab_media_keys(self) -> bool:
        """Tenta gravar teclas de mídia (requer permissão)."""
        if not self._media_keys_iface:
            return False
        try:
            await self._media_keys_iface.call_grab_media_player_keys("Naji", 0)
            return True
        except Exception:
            return False


class KDEGlobalShortcuts:
    """Integração com KDE Global Shortcuts (kglobalaccel)."""

    def __init__(self) -> None:
        self._bus: MessageBus | None = None

    async def connect(self) -> bool:
        if not DBUS_AVAILABLE:
            return False
        try:
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
            return True
        except Exception:
            return False


async def get_default_audio_sink() -> str | None:
    """Obtém sink de áudio padrão via PulseAudio/PipeWire (pactl)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "get-default-sink",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip()
    except Exception:
        pass
    return None


async def set_default_audio_sink(sink_name: str) -> bool:
    """Define sink de áudio padrão."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pactl", "set-default-sink", sink_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


def get_desktop_environment() -> str:
    """Detecta ambiente de desktop."""
    import os
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in de:
        return "gnome"
    elif "kde" in de or "plasma" in de:
        return "kde"
    elif "xfce" in de:
        return "xfce"
    elif "sway" in de or "hyprland" in de:
        return "wayland"
    return "unknown"
