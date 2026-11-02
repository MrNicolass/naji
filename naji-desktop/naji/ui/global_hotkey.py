"""Hotkey global de PTT (Windows e Linux).

Windows:
- Primário: hook de baixo nível (WH_KEYBOARD_LL) — detecta pressionar/soltar
  reais (push-to-talk de verdade). O RegisterHotKey sozinho não entrega
  key-up, então não consegue implementar "segurar para falar".
- Fallback: RegisterHotKey em janela message-only (modo toggle: uma
  pressionada inicia, outra termina).

Linux:
- Biblioteca `keyboard` (X11). Em Wayland ou sem permissão, o fallback é o
  botão PTT da UI.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from naji.config import Config

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SPACE = 0x20
VK_LWIN = 0x5B
VK_F1 = 0x70

_MODIFIER_VK = {
    MOD_CONTROL: VK_CONTROL,
    MOD_ALT: VK_MENU,
    MOD_SHIFT: VK_SHIFT,
    MOD_WIN: VK_LWIN,
}


def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Converte 'ctrl+alt+space' em (modifiers, vk_code)."""
    modifiers = 0
    vk = 0
    for part in (p.strip().lower() for p in hotkey_str.split("+")):
        if not part:
            continue
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part == "alt":
            modifiers |= MOD_ALT
        elif part == "shift":
            modifiers |= MOD_SHIFT
        elif part in ("win", "windows", "super", "meta"):
            modifiers |= MOD_WIN
        elif part == "space":
            vk = VK_SPACE
        elif part == "enter":
            vk = VK_RETURN
        elif part.startswith("f") and part[1:].isdigit():
            n = int(part[1:])
            if 1 <= n <= 24:
                vk = VK_F1 + n - 1
        elif len(part) == 1:
            vk = ord(part.upper())
    return modifiers, vk


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WH_KEYBOARD_LL = 13
    HC_ACTION = 0
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_HOTKEY = 0x0312

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    _HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

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

    user32.DefWindowProcW.restype = ctypes.c_long
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
    ]
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, ctypes.c_uint]
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    user32.CallNextHookEx.restype = ctypes.c_long
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

    _hook_refs: list[_HOOKPROC] = []
    _wnd_proc_refs: list[_WNDPROC] = []

    class WindowsHotkeyBackend:
        """PTT global no Windows.

        Primário: WH_KEYBOARD_LL (pressionar/soltar reais).
        Fallback: RegisterHotKey em janela message-only (modo toggle).
        """

        _HOTKEY_ID = 1

        def __init__(self, on_pressed: Callable[[], None], on_released: Callable[[], None]) -> None:
            self._on_pressed = on_pressed
            self._on_released = on_released
            self._hook = 0
            self._hwnd = 0
            self._modifiers = 0
            self._vk = 0
            self._held = False
            self._toggle_mode = False
            self._proc_ref: _HOOKPROC | None = None
            self._wnd_proc_ref: _WNDPROC | None = None

        def install(self, modifiers: int, vk: int) -> tuple[bool, str]:
            self._modifiers = modifiers
            self._vk = vk

            self._proc_ref = _HOOKPROC(self._hook_callback)
            _hook_refs.append(self._proc_ref)
            self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc_ref, None, 0)
            if self._hook:
                return True, "keyboard-hook"
            return self._install_toggle(modifiers, vk)

        def _install_toggle(self, modifiers: int, vk: int) -> tuple[bool, str]:
            """Fallback: RegisterHotKey em janela oculta 0x0 (modo toggle).

            Parent NULL + tamanho 0x0: janela invisível, sem taskbar/Alt-Tab.
            HWND_MESSAGE foi evitado porque falha com ERROR_INVALID_WINDOW_HANDLE
            em algumas sessões (validado em 01/11/2026).
            """
            self._toggle_mode = True
            self._wnd_proc_ref = _WNDPROC(self._wnd_proc)
            _wnd_proc_refs.append(self._wnd_proc_ref)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wnd_proc_ref
            wc.hInstance = kernel32.GetModuleHandleW(None)
            wc.lpszClassName = "NajiHotkeyWindow"
            atom = user32.RegisterClassW(ctypes.byref(wc))
            self._hwnd = user32.CreateWindowExW(
                0, atom, "NajiHotkey", 0, 0, 0, 0, 0,
                None, None, wc.hInstance, None,
            )
            ok = user32.RegisterHotKey(self._hwnd, self._HOTKEY_ID, modifiers, vk)
            return bool(ok), "register-hotkey-toggle"

        def _modifiers_down(self) -> bool:
            for flag, vk_code in _MODIFIER_VK.items():
                if self._modifiers & flag and not (user32.GetAsyncKeyState(vk_code) & 0x8000):
                    return False
            return True

        def _hook_callback(self, n_code: int, wparam: int, lparam: int) -> int:
            try:
                if n_code == HC_ACTION:
                    msg = int(wparam)
                    if msg in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
                        data = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                        if data.vkCode == self._vk:
                            if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                                if not self._held and self._modifiers_down():
                                    self._held = True
                                    self._on_pressed()
                            elif self._held:
                                self._held = False
                                self._on_released()
            except Exception:
                pass
            return user32.CallNextHookEx(self._hook, n_code, wparam, lparam)

        def _wnd_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_HOTKEY and wparam == self._HOTKEY_ID:
                if self._held:
                    self._held = False
                    self._on_released()
                else:
                    self._held = True
                    self._on_pressed()
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        def uninstall(self) -> None:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = 0
            if self._toggle_mode and self._hwnd:
                user32.UnregisterHotKey(self._hwnd, self._HOTKEY_ID)
                user32.DestroyWindow(self._hwnd)
                self._hwnd = 0
            self._held = False

else:
    class LinuxHotkeyBackend:
        """PTT global no Linux via `keyboard` (X11). Fallback: botão PTT da UI."""

        def __init__(self, on_pressed: Callable[[], None], on_released: Callable[[], None]) -> None:
            self._on_pressed = on_pressed
            self._on_released = on_released
            self._keyboard = None
            self._held = False

        def install(self, hotkey_str: str) -> tuple[bool, str]:
            try:
                import keyboard
            except ImportError:
                return False, "none"
            try:
                keyboard.add_hotkey(hotkey_str, self._on_down)
                release_key = hotkey_str.split("+")[-1].strip()
                keyboard.on_release_key(release_key, self._on_up)
                self._keyboard = keyboard
                return True, "keyboard"
            except Exception:
                self._keyboard = None
                return False, "none"

        def _on_down(self) -> None:
            if not self._held:
                self._held = True
                self._on_pressed()

        def _on_up(self) -> None:
            if self._held:
                self._held = False
                self._on_released()

        def uninstall(self) -> None:
            if self._keyboard is not None:
                try:
                    self._keyboard.unhook_all()
                except Exception:
                    pass
                self._keyboard = None
            self._held = False


class GlobalHotkeyManager(QObject):
    """Gerenciador unificado da hotkey global de PTT."""

    ptt_pressed = Signal()
    ptt_released = Signal()
    backend_changed = Signal(str)

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._backend: WindowsHotkeyBackend | LinuxHotkeyBackend | None = None
        self._backend_name = "none"

    @property
    def active(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def start(self) -> bool:
        if self._backend is not None:
            return True
        hotkey = self._config.ui.hotkey
        if sys.platform == "win32":
            modifiers, vk = parse_hotkey(hotkey)
            if vk == 0:
                return False
            backend: WindowsHotkeyBackend | LinuxHotkeyBackend = WindowsHotkeyBackend(
                self._emit_pressed, self._emit_released
            )
            ok, name = backend.install(modifiers, vk)
        else:
            backend = LinuxHotkeyBackend(self._emit_pressed, self._emit_released)
            ok, name = backend.install(hotkey)
        if ok:
            self._backend = backend
            self._backend_name = name
            self.backend_changed.emit(name)
        return ok

    def stop(self) -> None:
        if self._backend is None:
            return
        self._backend.uninstall()
        self._backend = None
        self._backend_name = "none"
        self.backend_changed.emit("none")

    def _emit_pressed(self) -> None:
        self.ptt_pressed.emit()

    def _emit_released(self) -> None:
        self.ptt_released.emit()
