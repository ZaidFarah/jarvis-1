# Jarvis Windows AI Assistant

Jarvis is a Windows desktop AI assistant prototype focused on local-first voice control, a PySide6 HUD interface, explicit permissions, and safe whitelisted tools.

This is a portfolio checkpoint, not an unrestricted autonomous desktop agent. Risky actions are gated, shell access is not exposed through the assistant, and credentials/local runtime files are intentionally excluded.

## What It Demonstrates

- Desktop application development with Python and PySide6.
- Voice-first interaction design with speech-to-text and text-to-speech provider options.
- Local command routing with explicit permissions and whitelisted actions.
- Screen-vision and OCR workflow foundations with confirmation gates.
- Local reminders, memory and workflow support using SQLite-backed storage.
- Optional Gmail/Google Calendar integration foundations behind explicit local OAuth setup.
- Developer diagnostics, runtime checks, packaging scripts and test coverage.

## Main Features

- Red HUD-style desktop GUI with transcript, response, timing, voice state, workflow and developer panels.
- Fast voice command path with one-command capture, validation, optional OpenAI response streaming and optional TTS.
- Wake-word voice loop support with local fallback options.
- Safe app launching, website opening/search, read-only file access and folder listing.
- Local reminder storage and manual checks.
- Session context and explicit long-term memory for approved user facts/preferences.
- Screen capture/OCR and OpenAI vision support after confirmation.
- Codex bridge that writes auditable task briefs without executing shell commands itself.
- Health, runtime, settings, logs, backup, installer and packaged-app diagnostics.

## Tech Stack

| Area | Tools |
|---|---|
| Language | Python |
| GUI | PySide6 |
| Voice | Faster Whisper, OpenAI STT/TTS optional, pyttsx3 optional |
| Storage | SQLite |
| Vision/OCR | Screenshot capture, OCR, optional OpenAI vision |
| Testing | pytest-style unit tests and runtime checks |
| Packaging | Windows batch scripts and packaged smoke checks |

## Project Structure

```text
app/          Application lifecycle and orchestration
assistant/    Core assistant logic, routing and memory integration
agent/        Command routing and tool coordination
gui/          PySide6 desktop interface
voice/        Speech-to-text, wake word and text-to-speech logic
vision/       Screenshot, OCR and screen-vision services
services/     Startup, notification and OpenAI service helpers
tools/        Whitelisted local tools and workflow helpers
config/       Settings and environment configuration
docs/         Architecture, roadmap and bridge notes
tests/        Unit and integration-style tests
main.py       Main application entry point
```

## Local Setup

Jarvis is developed for Windows with PowerShell.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

Optional integrations such as OpenAI, Gmail and Google Calendar require local environment variables or OAuth credential files. Do not commit `.env`, OAuth tokens, logs, local databases, screenshots, build outputs or credential files.

## Safety Notes

- The assistant uses explicit permissions and whitelisted actions.
- Credentials and OAuth tokens are ignored by Git and should stay local.
- Screen vision and sensitive workflows require confirmation gates.
- The Codex bridge writes local Markdown task briefs; it does not run shell commands by itself.
- This project is a local assistant prototype, not a production security boundary.

## Portfolio Summary

Jarvis demonstrates Python desktop engineering, voice interface design, local automation safety, provider-based service design, settings validation, diagnostics, and Windows packaging workflows.
