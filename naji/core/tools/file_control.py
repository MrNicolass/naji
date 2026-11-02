"""File and folder controls for the model tool registry.

Opening a path and creating a folder are safe actions. Deleting a file or an
empty folder is destructive and is registered as a dangerous tool that
requires explicit confirmation in the bar before it runs.

Paths are validated: they must be absolute and stay outside protected system
directories. Deletion only removes a single file or an empty folder, never a
whole tree, so a misheard command cannot wipe a directory recursively.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path


def _blocked_roots() -> list[Path]:
    """Return system directories that tools must never touch."""
    if sys.platform == "win32":
        drive = os.environ.get("SystemDrive", "C:").rstrip(":")
        return [
            Path(f"{drive}:\\Windows"),
            Path(f"{drive}:\\Program Files"),
            Path(f"{drive}:\\Program Files (x86)"),
            Path(f"{drive}:\\ProgramData"),
        ]
    return [
        Path("/etc"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/boot"),
        Path("/sys"),
        Path("/proc"),
        Path("/dev"),
        Path("/lib"),
        Path("/lib64"),
        Path("/run"),
    ]


def validate_path(raw: str) -> Path | str:
    """Normalize a user-provided path or return an actionable error string."""
    text = (raw or "").strip()
    if not text:
        return "Error: a path is required."
    path = Path(text).expanduser()
    if not path.is_absolute():
        return "Error: the path must be absolute, e.g. C:\\Users\\me\\notes.txt or /home/me/notes.txt"
    resolved = path.resolve()
    for root in _blocked_roots():
        if resolved == root or root in resolved.parents:
            return f"Error: {resolved} is inside a protected system directory."
    return resolved


async def open_path(path: str) -> str:
    """Open a file or folder with the system default application."""
    checked = validate_path(path)
    if isinstance(checked, str):
        return checked
    if not checked.exists():
        return f"Error: {checked} does not exist."
    if sys.platform == "win32":
        try:
            os.startfile(str(checked))  # type: ignore[attr-defined]
        except OSError as exc:
            return f"Error: could not open {checked}: {exc}"
        return f"Opened {checked}."
    if shutil.which("xdg-open") is None:
        return "Error: opening files requires xdg-open to be installed on Linux."
    try:
        proc = await asyncio.create_subprocess_exec(
            "xdg-open",
            str(checked),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
    except Exception as exc:
        return f"Error: could not open {checked}: {exc}"
    return f"Opened {checked}."


async def create_folder(path: str) -> str:
    """Create a new folder at the given path."""
    checked = validate_path(path)
    if isinstance(checked, str):
        return checked
    if checked.exists():
        if checked.is_dir():
            return f"Folder {checked} already exists."
        return f"Error: cannot create folder {checked}: a file with that name already exists."
    try:
        checked.mkdir()
    except OSError as exc:
        return f"Error: could not create folder {checked}: {exc}"
    return f"Created folder {checked}."


async def delete_path(path: str) -> str:
    """Delete a file or an empty folder. Requires user confirmation."""
    checked = validate_path(path)
    if isinstance(checked, str):
        return checked
    if not checked.exists():
        return f"Error: {checked} does not exist."
    try:
        if checked.is_dir():
            if any(checked.iterdir()):
                return f"Error: folder {checked} is not empty. Empty it before deleting it."
            checked.rmdir()
            return f"Deleted folder {checked}."
        checked.unlink()
    except OSError as exc:
        return f"Error: could not delete {checked}: {exc}"
    return f"Deleted {checked}."


def get_open_path_schema() -> dict:
    """Return the OpenAI function-calling schema for opening a file or folder."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="open_path",
        description=(
            "Open a file or a folder with the system default application. "
            "Accepts an absolute path. Use it when the user asks to open, "
            "show or reveal a file or a folder."
        ),
        parameters={
            "path": {
                "type": "string",
                "description": "Absolute path of the file or folder to open.",
            },
        },
        required=["path"],
    )


def get_create_folder_schema() -> dict:
    """Return the OpenAI function-calling schema for creating a folder."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="create_folder",
        description=(
            "Create a new folder at the given absolute path. The parent "
            "folder must already exist. Use it when the user asks to create "
            "or make a folder."
        ),
        parameters={
            "path": {
                "type": "string",
                "description": "Absolute path of the folder to create.",
            },
        },
        required=["path"],
    )


def get_delete_path_schema() -> dict:
    """Return the OpenAI function-calling schema for deleting a file or folder."""
    from naji.core.tools import create_tool_schema

    return create_tool_schema(
        name="delete_path",
        description=(
            "Delete a file, or an empty folder, at the given absolute path. "
            "Folders must be empty; this never deletes a whole tree. Deleting "
            "is permanent and requires user confirmation."
        ),
        parameters={
            "path": {
                "type": "string",
                "description": "Absolute path of the file or empty folder to delete.",
            },
        },
        required=["path"],
    )
