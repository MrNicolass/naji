"""Controle de mídia nativo (Windows VK / Linux MPRIS2)."""

from __future__ import annotations

import sys
from typing import Literal

if sys.platform == "win32":
    import ctypes

    user32 = ctypes.windll.user32

    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002


def _send_media_key_windows(vk: int) -> None:
    """Envia tecla de mídia via keybd_event (global, sem foco)."""
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


async def media_control(action: Literal["play_pause", "next", "previous"]) -> str:
    """
    Controla mídia do sistema.

    Args:
        action: "play_pause" | "next" | "previous"

    Returns:
        String descrevendo a ação executada.
    """
    if sys.platform == "win32":
        mapping = {
            "play_pause": VK_MEDIA_PLAY_PAUSE,
            "next": VK_MEDIA_NEXT_TRACK,
            "previous": VK_MEDIA_PREV_TRACK,
        }
        _send_media_key_windows(mapping[action])
        return f"Mídia: {action.replace('_', ' ')} executado (Windows VK)"

    # Linux: MPRIS2 via dbus-next
    try:
        from dbus_next.aio import MessageBus
        from dbus_next.constants import BusType

        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect("org.mpris.MediaPlayer2.spotify", "/org/mpris/MediaPlayer2")
        # Tenta players comuns
        players = [
            "org.mpris.MediaPlayer2.spotify",
            "org.mpris.MediaPlayer2.firefox",
            "org.mpris.MediaPlayer2.chrome",
            "org.mpris.MediaPlayer2.vlc",
            "org.mpris.MediaPlayer2.mpv",
        ]

        for player in players:
            try:
                obj = bus.get_proxy_object(player, "/org/mpris/MediaPlayer2", introspection)
                player_iface = obj.get_interface("org.mpris.MediaPlayer2.Player")
                mapping = {
                    "play_pause": "PlayPause",
                    "next": "Next",
                    "previous": "Previous",
                }
                await getattr(player_iface, mapping[action])()
                return f"Mídia: {action.replace('_', ' ')} executado (MPRIS2: {player})"
            except Exception:
                continue

        return "Erro: nenhum player MPRIS2 encontrado"
    except Exception as exc:
        return f"Erro MPRIS2: {type(exc).__name__}: {exc}"


def get_media_control_schema() -> dict:
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="media_control",
        description="Controla reprodução de mídia do sistema (play/pause, próxima, anterior).",
        parameters={
            "action": {
                "type": "string",
                "enum": ["play_pause", "next", "previous"],
                "description": "Ação a executar",
            }
        },
        required=["action"],
    )
