# Naji

Tray-first desktop voice assistant. Naji stays in the system tray and opens a
small floating bar at the bottom center when summoned by a global hotkey. The
configured model does the reasoning and calls native tools; the interface only
exposes transport controls.

## Requirements

- Python 3.11+
- Windows 10/11 (primary) or Linux/X11
- A llama.cpp server exposing `/v1/realtime`, `/v1/chat/completions` and `/tts`

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m naji             # tray only
python -m naji --show      # open the bar on startup
python -m naji --debug     # verbose logs
python -m naji --smoke-test
```

The first run creates `%LOCALAPPDATA%\Naji\config.yaml` on Windows (or
`~/.config/Naji/config.yaml` on Linux). Environment variables override the file:

```text
NAJI_SERVER__API_KEY=...
NAJI_UI__HOTKEY=ctrl+alt+space
NAJI_UI__THEME=system
```

Logs: `%LOCALAPPDATA%\Naji\logs\naji.log` (rotating).

## Test and lint

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check naji tests
```

Integration tests against `http://localhost:9931/v1` are skipped automatically
when the server is offline.

## Build

```powershell
.\.venv\Scripts\python.exe -m PyInstaller naji.spec --noconfirm --clean
```

The onefile executable is written to `dist\naji.exe`.

## Layout

```text
.
  naji/
    app.py              # bootstrap: QApplication, qasync, single instance
    config.py           # Pydantic settings v2 + YAML + env
    controller/         # tray/bar/hotkey wiring
    core/               # realtime client, audio, tools
    i18n/               # pt-BR and en dictionaries
    ui/                 # bar, tray, theme tokens and QSS
    platform/           # Windows/Linux helpers and autostart
  tests/
```

Design and architecture decisions live in the Obsidian vault under
`Pessoal/Projetos/Naji/`, not in this repository.
