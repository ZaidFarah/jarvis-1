# PyInstaller Notes

Phase 36 only prepares Jarvis for packaging.

Current build intent:

- Entry point: `main.py`
- App name: `Jarvis`
- Runtime mode: `source` by default, `packaged` when running from a frozen executable
- Runtime data folders: `logs/`, `data/`, `credentials/`, `assets/`

Recommended future command:

```powershell
pyinstaller --noconfirm --clean --onefile --windowed main.py
```

Do not run PyInstaller yet in this phase. The build script and runtime path helper exist so the next phase can package Jarvis without changing application behavior.
