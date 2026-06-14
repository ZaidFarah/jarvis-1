# Jarvis v0.1.0 Release Notes

## Major Features

- Windows EXE packaging with packaged smoke testing.
- External packaged config initialization under `%APPDATA%\Jarvis`.
- Safe startup registration for the current user.
- Safe settings editor for common non-secret options.
- Safe log viewer for local logs.
- Local backup and restore support.
- Installer preparation for Inno Setup.
- Signing readiness checks without requiring a certificate.

## Safety Model

- Permission broker classifies sensitive actions.
- Confirmation is required for medium and high risk actions.
- Secrets are not bundled into release ZIPs.
- Logs, data, and credentials are excluded from release packaging.
- Sensitive values are redacted in diagnostics where appropriate.

## Packaging Status

- `dist\Jarvis\Jarvis.exe` is built successfully.
- Release ZIP creation is supported.
- Installer preparation exists.
- Code-signing preparation exists.

## Known Limitations

- EXE and installer are unsigned.
- Installer build is unavailable unless Inno Setup is installed locally.
- Code signing is not enabled yet.
- Optional integrations require user-provided OAuth or API setup.

## Setup After Install

1. Run `Jarvis.exe --init-config`.
2. Put API keys in `%APPDATA%\Jarvis.env`.
3. Put Google client secret files in `%APPDATA%\Jarvis\credentials` only if needed.
4. Review `logs\`, `data\`, and `credentials\` paths in the runtime check.

## Not Included Yet

- Code signing certificates.
- Installer signing.
- Auto-updater.
- Windows services.
- Task Scheduler startup.
- Cloud backup or sync.
- Autonomous behavior.
