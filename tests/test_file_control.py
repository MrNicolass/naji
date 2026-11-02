"""Offline tests for the file and folder control tools."""

from __future__ import annotations

from pathlib import Path

import naji.core.tools.file_control as file_tool
from naji.core.tools.file_control import (
    create_folder,
    delete_path,
    get_create_folder_schema,
    get_delete_path_schema,
    get_open_path_schema,
    open_path,
    validate_path,
)


def test_file_schemas() -> None:
    schemas = {
        "open_path": get_open_path_schema(),
        "create_folder": get_create_folder_schema(),
        "delete_path": get_delete_path_schema(),
    }
    for name, schema in schemas.items():
        assert schema["name"] == name
        assert schema["parameters"]["required"] == ["path"]
    assert "confirmation" in get_delete_path_schema()["description"].lower()
    assert "confirmation" not in get_open_path_schema()["description"].lower()
    assert "confirmation" not in get_create_folder_schema()["description"].lower()


def test_validate_path_requires_absolute() -> None:
    result = validate_path("notes.txt")
    assert isinstance(result, str)
    assert "absolute" in result


def test_validate_path_rejects_blank() -> None:
    result = validate_path("   ")
    assert isinstance(result, str)
    assert "path is required" in result


def test_validate_path_accepts_user_path(tmp_path: Path) -> None:
    result = validate_path(str(tmp_path / "file.txt"))
    assert result == (tmp_path / "file.txt").resolve()


def test_validate_path_blocks_system_directories() -> None:
    root = file_tool._blocked_roots()[0]
    result = validate_path(str(root / "subdir"))
    assert isinstance(result, str)
    assert "protected" in result


async def test_create_folder_creates(tmp_path: Path) -> None:
    target = (tmp_path / "nova").resolve()

    result = await create_folder(str(tmp_path / "nova"))

    assert result == f"Created folder {target}."
    assert target.is_dir()


async def test_create_folder_already_exists(tmp_path: Path) -> None:
    target = tmp_path / "exists"
    target.mkdir()

    result = await create_folder(str(target))

    assert result == f"Folder {target.resolve()} already exists."


async def test_create_folder_parent_missing(tmp_path: Path) -> None:
    result = await create_folder(str(tmp_path / "missing" / "child"))

    assert result.startswith("Error:")
    assert not (tmp_path / "missing" / "child").exists()


async def test_delete_file(tmp_path: Path) -> None:
    target = tmp_path / "lixo.txt"
    target.write_text("x", encoding="utf-8")

    result = await delete_path(str(target))

    assert result == f"Deleted {target.resolve()}."
    assert not target.exists()


async def test_delete_empty_folder(tmp_path: Path) -> None:
    target = tmp_path / "vazia"
    target.mkdir()

    result = await delete_path(str(target))

    assert result == f"Deleted folder {target.resolve()}."
    assert not target.exists()


async def test_delete_nonempty_folder_refused(tmp_path: Path) -> None:
    target = tmp_path / "cheia"
    target.mkdir()
    (target / "arquivo.txt").write_text("x", encoding="utf-8")

    result = await delete_path(str(target))

    assert "not empty" in result
    assert target.exists()
    assert (target / "arquivo.txt").exists()


async def test_delete_missing(tmp_path: Path) -> None:
    result = await delete_path(str(tmp_path / "inexistente"))

    assert "does not exist" in result


async def test_open_path_windows(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "doc.txt"
    target.write_text("x", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(file_tool.sys, "platform", "win32")
    monkeypatch.setattr(file_tool.os, "startfile", lambda p: opened.append(p), raising=False)

    result = await open_path(str(target))

    assert result == f"Opened {target.resolve()}."
    assert opened == [str(target.resolve())]


async def test_open_path_linux_uses_xdg_open(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "doc.txt"
    target.write_text("x", encoding="utf-8")
    created: list[list[str]] = []
    monkeypatch.setattr(file_tool.sys, "platform", "linux")
    monkeypatch.setattr(file_tool.shutil, "which", lambda name: "/usr/bin/xdg-open")

    class FakeProc:
        returncode = 0

        async def wait(self) -> int:
            return 0

    async def fake_exec(*cmd: str, **kwargs: object) -> FakeProc:
        created.append(list(cmd))
        return FakeProc()

    monkeypatch.setattr(file_tool.asyncio, "create_subprocess_exec", fake_exec)

    result = await open_path(str(target))

    assert result == f"Opened {target.resolve()}."
    assert created == [["xdg-open", str(target.resolve())]]


async def test_open_path_linux_without_xdg_open(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "doc.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(file_tool.sys, "platform", "linux")
    monkeypatch.setattr(file_tool.shutil, "which", lambda name: None)

    result = await open_path(str(target))

    assert result.startswith("Error:")
    assert "xdg-open" in result


async def test_open_path_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(file_tool.sys, "platform", "win32")

    result = await open_path(str(tmp_path / "inexistente.txt"))

    assert "does not exist" in result
