# Agent notes

Source root: repository root.

## Commands

```powershell
.\.venv\Scripts\python.exe -m ruff check naji tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m naji --smoke-test
.\.venv\Scripts\python.exe -m PyInstaller naji.spec --noconfirm --clean
```

## Rules

- Do not commit unless the user explicitly asks.
- Do not add a main window. Naji is tray-first; the bar is a `Qt.Tool` window
  with no taskbar entry.
- UI text comes from `naji/i18n/` (PT-BR and EN must stay in parity). Do not
  hardcode user-facing strings.
- Colors, spacing and radii come from `naji/ui/theme/tokens.py`; do not
  hardcode visual values in widgets or QSS.
- Assistant capabilities are model tools. Do not add user-facing buttons for
  weather, time, media or search. Only transport/configuration controls belong
  in the bar, plus destructive-tool confirmation.
- Keep the `--smoke-test` flag working; it is the fast end-to-end check.
