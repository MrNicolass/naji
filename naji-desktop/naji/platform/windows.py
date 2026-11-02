"""Utilitários específicos do Windows."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    raise ImportError("Este módulo é apenas para Windows")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Constantes
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

HWND_BROADCAST = 0xFFFF
WM_APPCOMMAND = 0x319
APPCOMMAND_VOLUME_MUTE = 0x80000
APPCOMMAND_VOLUME_DOWN = 0x90000
APPCOMMAND_VOLUME_UP = 0xA0000
APPCOMMAND_MEDIA_PLAY_PAUSE = 0xE0000
APPCOMMAND_MEDIA_NEXT = 0xB0000
APPCOMMAND_MEDIA_PREVIOUS = 0xC0000


def send_media_key(vk: int) -> None:
    """Envia tecla de mídia global (keybd_event)."""
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def send_app_command(cmd: int) -> None:
    """Envia WM_APPCOMMAND para controle de volume/mídia."""
    user32.SendMessageW(HWND_BROADCAST, WM_APPCOMMAND, 0, cmd)


def media_play_pause() -> None:
    send_media_key(VK_MEDIA_PLAY_PAUSE)


def media_next() -> None:
    send_media_key(VK_MEDIA_NEXT_TRACK)


def media_previous() -> None:
    send_media_key(VK_MEDIA_PREV_TRACK)


def volume_mute() -> None:
    send_app_command(APPCOMMAND_VOLUME_MUTE)


def volume_down() -> None:
    send_app_command(APPCOMMAND_VOLUME_DOWN)


def volume_up() -> None:
    send_app_command(APPCOMMAND_VOLUME_UP)


def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, vk: int) -> bool:
    """Registra hotkey global."""
    return user32.RegisterHotKey(hwnd, hotkey_id, modifiers, vk)


def unregister_hotkey(hwnd: int, hotkey_id: int) -> bool:
    """Remove hotkey global."""
    return user32.UnregisterHotKey(hwnd, hotkey_id)


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_hidden_wnd_proc_refs: list[_WNDPROC] = []


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


def create_hidden_window(class_name: str = "NajiHiddenWindow") -> int:
    """Cria janela oculta 0x0 (parent NULL) para receber mensagens."""

    def wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_proc_ref = _WNDPROC(wnd_proc)
    _hidden_wnd_proc_refs.append(wnd_proc_ref)

    wc = WNDCLASSW()
    wc.lpfnWndProc = wnd_proc_ref
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.lpszClassName = class_name
    atom = user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(
        0, atom, class_name, 0, 0, 0, 0, 0,
        None, 0, wc.hInstance, None
    )
    return hwnd


def get_audio_devices() -> list[dict]:
    """Lista dispositivos de áudio (via sounddevice preferencialmente)."""
    # sounddevice já faz isso melhor
    return []


def set_process_dpi_aware() -> None:
    """Torna o processo DPI aware (para telas HiDPI)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE_V2
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def enable_ansi_colors() -> None:
    """Habilita cores ANSI no console Windows 10+."""
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
