"""Offline tests for the autostart platform helper."""

from __future__ import annotations

import sys
import types

import naji.platform.autostart as autostart


def _install_fake_winreg(monkeypatch, present: bool):
    calls: dict[str, list] = {"set": [], "deleted": []}
    store: dict[str, str] = {autostart.APP_NAME: "old-command"} if present else {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _open_key(_hive, path):
        assert path == autostart.RUN_KEY
        return _Key()

    def _create_key(_hive, path):
        assert path == autostart.RUN_KEY
        return _Key()

    def _query_value_ex(_key, name):
        if name not in store:
            raise FileNotFoundError(name)
        return (0, store[name])

    def _set_value_ex(_key, name, _reserved, reg_type, value):
        assert reg_type == 1
        calls["set"].append((name, value))
        store[name] = value

    def _delete_value(_key, name):
        if name not in store:
            raise FileNotFoundError(name)
        calls["deleted"].append(name)
        del store[name]

    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = object()
    fake.REG_SZ = 1
    fake.OpenKey = _open_key
    fake.CreateKey = _create_key
    fake.QueryValueEx = _query_value_ex
    fake.SetValueEx = _set_value_ex
    fake.DeleteValue = _delete_value
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(autostart, "os", types.SimpleNamespace(name="nt"))
    return calls, store


def test_launch_command_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", r"C:\Naji\naji.exe")

    assert autostart._launch_command() == r'"C:\Naji\naji.exe" --minimized'


def test_launch_command_unfrozen_prefers_pythonw(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python.exe"
    python.touch()
    pythonw = tmp_path / "pythonw.exe"
    pythonw.touch()
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(python))

    assert autostart._launch_command() == f'"{pythonw}" -m naji --minimized'


def test_launch_command_unfrozen_falls_back_to_python(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python.exe"
    python.touch()
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(autostart.sys, "executable", str(python))

    assert autostart._launch_command() == f'"{python}" -m naji --minimized'


def test_is_autostart_enabled_windows(monkeypatch) -> None:
    _install_fake_winreg(monkeypatch, present=True)

    assert autostart.is_autostart_enabled() is True


def test_is_autostart_disabled_windows(monkeypatch) -> None:
    _install_fake_winreg(monkeypatch, present=False)

    assert autostart.is_autostart_enabled() is False


def test_set_autostart_enables_windows(monkeypatch) -> None:
    calls, store = _install_fake_winreg(monkeypatch, present=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(autostart.sys, "executable", r"C:\Naji\naji.exe")

    autostart.set_autostart(True)

    expected = r'"C:\Naji\naji.exe" --minimized'
    assert store[autostart.APP_NAME] == expected
    assert calls["set"] == [(autostart.APP_NAME, expected)]


def test_set_autostart_disables_windows(monkeypatch) -> None:
    calls, store = _install_fake_winreg(monkeypatch, present=True)

    autostart.set_autostart(False)

    assert autostart.APP_NAME not in store
    assert calls["deleted"] == [autostart.APP_NAME]


def test_set_autostart_disable_missing_value_is_noop(monkeypatch) -> None:
    _install_fake_winreg(monkeypatch, present=False)

    autostart.set_autostart(False)


def _fake_linux(monkeypatch) -> None:
    monkeypatch.setattr(autostart, "os", types.SimpleNamespace(name="posix"))
    monkeypatch.setattr(autostart.sys, "platform", "linux")


def test_linux_autostart_writes_desktop_file(monkeypatch, tmp_path) -> None:
    desktop = tmp_path / "naji.desktop"
    _fake_linux(monkeypatch)
    monkeypatch.setattr(autostart, "LINUX_DESKTOP", desktop)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(autostart.sys, "executable", "/usr/bin/python3")

    autostart.set_autostart(True)

    assert autostart.is_autostart_enabled() is True
    content = desktop.read_text(encoding="utf-8")
    assert f"Exec={autostart._launch_command()}" in content
    assert "X-GNOME-Autostart-enabled=true" in content


def test_linux_autostart_removes_desktop_file(monkeypatch, tmp_path) -> None:
    desktop = tmp_path / "naji.desktop"
    desktop.write_text("[Desktop Entry]\n", encoding="utf-8")
    monkeypatch.setattr(autostart.os, "name", "posix")
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    monkeypatch.setattr(autostart, "LINUX_DESKTOP", desktop)

    autostart.set_autostart(False)

    assert not desktop.exists()
    assert autostart.is_autostart_enabled() is False
