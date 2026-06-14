# PyInstaller Notes

Phase 42 keeps the first Windows build, external config initialization, launcher scripts, packaged smoke tests, release readiness checks, and adds versioned manual ZIP creation.

Build command:

```powershell
cmd /c build_exe.bat
```

Build output:

```text
dist/Jarvis/Jarvis.exe
```

The build script runs a clean onedir build from `main.py`, includes `.env.example`, includes only `assets/` when present, and keeps the executable in console mode so CLI diagnostics such as `--version`, `--runtime-check`, `--health-check`, `--openai-check`, `--init-config`, and `--packaged-smoke-plan` still work.
In PyInstaller 6 onedir builds, bundled data is stored under the internal content directory, so packaged runtime checks report `assets/` under `dist/Jarvis/_internal/` when bundled assets exist. Mutable packaged config paths resolve to `%APPDATA%\Jarvis` and the packaged env file resolves to `%APPDATA%\Jarvis.env`.

Version:

```powershell
py main.py --version
dist\Jarvis\Jarvis.exe --version
```

The version comes from `jarvis_runtime/version.py` and defaults to `APP_VERSION=0.1.0`.

Release readiness:

```powershell
py main.py --release-check
```

The release check verifies the build script, optional built EXE, source runtime and health diagnostics, packaged smoke scripts, startup CLI commands, README sections, and tracked-file safety for `.env`, credentials, tokens, logs, and `data/*.db`.
Missing `dist/Jarvis/Jarvis.exe` is a warning so the check can be run before a build. Tracked secrets or generated local state are failures.

Release package check:

```powershell
py main.py --release-package-check
```

The package check verifies the expected ZIP path, release inputs, and exclusions without creating the archive.

Known limitations:

- No installer yet.
- No code signing yet.
- No updater yet.
- Startup registration is optional current-user Run-key registration only; there is no Windows service or Task Scheduler integration.
- No secrets, tokens, logs, or database files are packaged.
- `--init-config` copies `.env.example` to `%APPDATA%\Jarvis.env` only when the env file is missing.
- If `assets/jarvis.ico` is absent, the build runs without an icon.
- `packaging/` is documentation-only. Runtime packaging helpers live in `jarvis_runtime/` so PyInstaller can still import its third-party `packaging` dependency.

Known PyInstaller warnings:

- Optional ML backends may warn about missing `torch`, `tbb12.dll`, or TensorFlow plugin libraries.
- Optional generated parser modules such as `pycparser.lextab` and `pycparser.yacctab` may be reported as hidden imports.
- Optional SciPy internals such as `scipy.special._cdflib` may be reported as hidden imports.
- These warnings are non-fatal for the current smoke checks when `Jarvis.exe` builds and the runtime, health, and OpenAI diagnostics run.

Windows SmartScreen:

- The EXE is not code signed yet.
- Windows may show a SmartScreen warning for locally built unsigned executables.
- Use only builds produced from this working tree. Installer creation and signing are future phases.

How to test the EXE:

```powershell
dist\Jarvis\Jarvis.exe --version
dist\Jarvis\Jarvis.exe --runtime-check
dist\Jarvis\Jarvis.exe --health-check
dist\Jarvis\Jarvis.exe --openai-check
dist\Jarvis\Jarvis.exe --init-config
test_packaged_app.bat
py main.py --release-check
py main.py --release-package-check
```

Launcher scripts:

```powershell
run_jarvis.bat
run_jarvis_console.bat
test_packaged_app.bat
```

Manual ZIP release:

```powershell
create_release_zip.bat
```

Output:

```text
releases\Jarvis-0.1.0-windows.zip
```

The ZIP includes:

```text
dist\Jarvis\Jarvis.exe
dist\Jarvis\_internal\
README.md
run_jarvis.bat
run_jarvis_console.bat
test_packaged_app.bat
```

Do not add `.env`, `%APPDATA%\Jarvis.env`, credentials, tokens, logs, local databases, `.git`, `build/`, installer files, updater files, or signing artifacts to the ZIP.
