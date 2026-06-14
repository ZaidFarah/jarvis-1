# Code Signing Notes

Phase 47 prepares Jarvis for code signing without creating or storing any certificates.

## What code signing is

A code-signing certificate is used to attach a trusted publisher signature to an executable or installer. Windows can use that signature to reduce SmartScreen warnings and to show that the file came from the expected publisher.

## What this phase does

- Adds `SIGNING_ENABLED`, `SIGNING_CERT_PATH`, `SIGNING_TIMESTAMP_URL`, and `SIGNING_DESCRIPTION` settings.
- Adds readiness checks for `signtool.exe`, the packaged EXE, and the installer output.
- Adds helper scripts for signing the EXE and the installer later.
- Does not create certificates.
- Does not store certificate passwords.
- Does not sign anything unless signing is explicitly enabled.

## What you will need later

- A valid code-signing certificate from a trusted certificate authority.
- `signtool.exe` from the Windows SDK.
- A timestamp server URL.
- A certificate file or certificate store entry that the build machine can access.

## SmartScreen

Unsigned Jarvis builds can trigger SmartScreen warnings. That is expected until the app and installer are signed with a trusted certificate.
