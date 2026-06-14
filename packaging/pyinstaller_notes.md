# PyInstaller Notes

Phase 37 adds the first Windows build of Jarvis.

Build command:

```powershell
cmd /c build_exe.bat
```

Build output:

```text
dist/Jarvis/Jarvis.exe
```

The build script runs a clean onedir build from `main.py`, includes only `assets/` when present, and keeps the executable in console mode so CLI diagnostics such as `--runtime-check` and `--health-check` still work.
In PyInstaller 6 onedir builds, bundled data is stored under the internal content directory, so packaged runtime checks report `assets/` under `dist/Jarvis/_internal/` when bundled assets exist. Mutable runtime paths still resolve beside `Jarvis.exe`.

Known limitations:

- No installer yet.
- No code signing yet.
- No startup service yet.
- No secrets, tokens, logs, or database files are packaged.
- If `assets/jarvis.ico` is absent, the build runs without an icon.
- `packaging/` is documentation-only. Runtime packaging helpers live in `jarvis_runtime/` so PyInstaller can still import its third-party `packaging` dependency.

How to test the EXE:

```powershell
dist\Jarvis\Jarvis.exe --runtime-check
dist\Jarvis\Jarvis.exe --health-check
```
