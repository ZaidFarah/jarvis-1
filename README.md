# Jarvis

Jarvis is a Windows desktop AI assistant checkpoint focused on local-first voice, a red HUD GUI, explicit permissions, and safe whitelisted tools.

This repository is being prepared as the v0.3.0 stable checkpoint. It is not an autonomous desktop agent: risky actions are gated, shell access is not exposed through the assistant, and browser/desktop automation is not implemented.

## Current Features

- PySide6 red HUD GUI with an animated assistant core, voice-first controls, a compact command bar, tray menu, voice state, transcript, response, timing, screen vision, developer, and workflow panels.
- Fast GUI voice path with one-command capture, speech repair, local validation, optional OpenAI streaming text, and optional TTS.
- Legacy wake-based voice loop with wake detection, command retry, follow-up listening, concise voice responses, and turn diagnostics.
- Speech-to-text support through Faster Whisper by default, with an OpenAI STT provider foundation and Faster Whisper fallback.
- Text-to-speech support through OpenAI TTS or local `pyttsx3`, disabled by default for GUI fast voice.
- Short-term conversation history and SQLite long-term memory for explicit personal facts and preferences.
- Local reminders with manual checks, optional watcher, optional notifications, and SQLite storage.
- Safe whitelisted app launching, website opening/search, folder listing, and read-only file access.
- Multi-monitor screen vision with screenshot capture, OCR, resized OpenAI vision uploads, and timeout-aware fallback after confirmation.
- Google Calendar and Gmail foundations behind explicit enablement, OAuth setup, permission checks, and confirmations.
- Developer tools for git status, last commit, fast tests, project file opens, and VS Code open from terminal commands and the GUI Developer panel.
- Safe local workflow engine for fixed multi-step coding-session and work-review flows built from the existing developer tools, with a compact workflow panel in the GUI.
- Health, runtime, settings, logs, backup, release, installer, signing, and packaged smoke diagnostics.

## Setup

Jarvis is developed and tested on Windows with PowerShell.

1. Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

3. Create local configuration:

```powershell
Copy-Item .env.example .env
```

4. Start the GUI:

```powershell
python main.py
```

Packaged builds can initialize external config under `%APPDATA%`:

```powershell
dist\Jarvis\Jarvis.exe --init-config
dist\Jarvis\Jarvis.exe --runtime-check
```

## Recommended `.env`

Use `.env.example` as the source of truth. For a stable local v0.3.0-style checkpoint, these are the practical defaults to review first:
For GUI voice testing, keep `FAST_VOICE_TTS_MODE=off` unless you are explicitly testing spoken output.

```dotenv
APP_NAME=Jarvis
GUI_VOICE_ENGINE=fast
GUI_STREAM_RESPONSE=true

OPENAI_ENABLED=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini

FAST_VOICE_ENABLED=true
FAST_VOICE_ACTIVATION=enter
FAST_VOICE_TTS_MODE=off
FAST_VOICE_STREAM_OPENAI=true
FAST_VOICE_CONCISE_RESPONSES=true

STT_PROVIDER=faster_whisper
STT_FALLBACK_PROVIDER=faster_whisper
OPENAI_STT_MODEL=gpt-4o-mini-transcribe
STT_BENCHMARK_SECONDS=5.0
WHISPER_MODEL=base.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

WAKE_PROVIDER=openwakeword
WAKE_FALLBACK_PROVIDER=whisper_fuzzy
WAKE_PHRASE=hey jarvis

VOICE_RESPONSE_MODE=concise
VOICE_LOOP_SPEAK_WAKE_ACK=false
VOICE_LOOP_SPEAK_RESPONSES=true
VOICE_LOOP_SPEAK_STANDBY=false

MEMORY_ENABLED=true
MEMORY_CONFIRM_NAMES=true
MEMORY_DB_PATH=memory.db

REMINDERS_ENABLED=true
REMINDERS_CHECK_ENABLED=true
REMINDERS_WATCH_ENABLED=false

APP_LAUNCHER_ENABLED=true
WEBSITE_LAUNCHER_ENABLED=true
FILE_ACCESS_ENABLED=true
FILE_READ_ENABLED=false
FILE_SUMMARY_ENABLED=false

VISION_ENABLED=true
SCREEN_VISION_ENABLED=true
SCREENSHOT_ENABLED=true
OCR_ENABLED=true
OPENAI_VISION_ENABLED=true
OPENAI_VISION_TIMEOUT_SECONDS=15
OPENAI_VISION_MAX_WIDTH=1280
OPENAI_VISION_JPEG_QUALITY=75
SCREENSHOT_DIR=data/screenshots

CONFIRMATION_REQUIRED=true
DEVELOPER_MODE_ENABLED=true
DEVELOPER_COMMAND_TIMEOUT_SECONDS=120

CALENDAR_ENABLED=false
GMAIL_ENABLED=false
WEATHER_ENABLED=false
NOTIFICATIONS_ENABLED=false
TTS_ENABLED=false
```

Keep `.env`, OAuth tokens, credentials, logs, local databases, screenshots, and build outputs out of Git.

## Main Commands

Run the app and common checks:

```powershell
python main.py
python main.py --version
python main.py --settings-check
python main.py --health-check
python main.py --runtime-check
python main.py --logs-list
```

Voice and audio:

```powershell
python main.py --audio-check
python main.py --voice-health-check
python main.py --transcribe-test
python main.py --stt-benchmark
python main.py --stt-benchmark-file "logs\audio\sample.wav"
python main.py --wake-provider-check
python main.py --openwakeword-test
python main.py --command-capture-test
python main.py --voice-command-test
python main.py --fast-command-test
python main.py --fast-voice
python main.py --voice-loop
```

Assistant, memory, reminders, and notifications:

```powershell
python main.py --chat-test "Say hello"
python main.py --chat-session
python main.py --memory-test
python main.py --reminders-test
python main.py --reminders-check
python main.py --reminders-watch
python main.py --notification-check
```

Safe local tools:

```powershell
python main.py --app-launcher-check
python main.py --resolve-app notepad
python main.py --launch-app notepad
python main.py --website-check
python main.py --open-site google
python main.py --file-access-check
python main.py --list-folder downloads
python main.py --find-file "report" downloads
python main.py --read-file "notes.txt" documents
python main.py --summarize-file "notes.txt" documents
```

Screen vision:

```powershell
python main.py --vision-check
python main.py --screenshot-test
python main.py --ocr-test "data\screenshots\example.png"
python main.py --vision-analyze "data\screenshots\example.png"
```

Calendar and Gmail:

```powershell
python main.py --calendar-check
python main.py --calendar-auth
python main.py --calendar-today
python main.py --calendar-create "Meeting" "2026-06-12 18:30" 30
python main.py --gmail-check
python main.py --gmail-auth
python main.py --gmail-unread
python main.py --gmail-draft "person@example.com" "Subject" "Body text"
python main.py --gmail-drafts
python main.py --gmail-send-draft draft-id
```

Release and maintenance:

```powershell
python main.py --backup-create
python main.py --backup-list
python main.py --release-check
python main.py --release-package-check
python main.py --installer-check
python main.py --signing-check
python main.py --final-report
python main.py --release-notes
```

Developer workflow inside Jarvis:

```text
run tests
run pytest
run fast tests
check git status
show git status
show last commit
open main.py
open assistant core
open settings
open tests folder
open jarvis in vs code
start coding session
review today's work
```

The workflow commands are fixed plans only. `start coding session` opens Jarvis in VS Code, checks git status, runs fast tests, and summarizes the result. `review today's work` checks git status, shows the last commit, runs fast tests, and summarizes the result.

The GUI Developer panel exposes the same safe developer service for git status, last commit, fast tests, project files, the tests folder, and VS Code.

## Troubleshooting

If the GUI does not start:

- Run `python -m py_compile main.py`.
- Run `python main.py --settings-check`.
- Check `logs/jarvis.log` or run `python main.py --logs-list`.
- Verify PySide6 is installed in the active virtual environment.

If microphone or STT is not working:

- Run `python main.py --audio-check` and `python main.py --voice-health-check`.
- Confirm the Windows default input device and `VOICE_INPUT_DEVICE`.
- Use `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8` for the safest CPU path.
- Install or repair Faster Whisper dependencies if `--transcribe-test` cannot load the model.
- Keep `FAST_VOICE_TTS_MODE=off` while testing command routing to avoid slow TTS masking routing issues.

If wake word is unreliable:

- Run `python main.py --wake-provider-check`.
- Use `WAKE_PROVIDER=openwakeword` with `WAKE_FALLBACK_PROVIDER=whisper_fuzzy`.
- Run `python main.py --openwakeword-test` for diagnostics.
- Lower thresholds carefully only after checking false positives.

If OpenAI features do not respond:

- Set `OPENAI_ENABLED=true`.
- Add `OPENAI_API_KEY` locally in `.env`.
- Run `python main.py --openai-check`.
- Keep OpenAI vision and TTS separately enabled only when needed.

If screen vision fails:

- Run `python main.py --vision-check`.
- Confirm `SCREENSHOT_DIR=data/screenshots`.
- Install/configure Tesseract if OCR is needed.
- Expect confirmation prompts before screenshot capture or image upload.

If Gmail or Calendar fails:

- Keep `GMAIL_ENABLED=false` and `CALENDAR_ENABLED=false` until OAuth is configured.
- Put the Google OAuth client secret at `credentials/google_client_secret.json`.
- Run `python main.py --gmail-auth` or `python main.py --calendar-auth`.
- Re-run auth after enabling write/send scopes.

If developer buttons do nothing:

- Confirm `DEVELOPER_MODE_ENABLED=true`.
- Use the GUI Developer panel, terminal developer commands, or the fixed workflow commands.
- Check `logs/developer.log`.
- Fast tests are intentionally limited to a whitelisted test subset.

## Validation

Recommended release-prep validation:

```powershell
python -m py_compile main.py
python -m pytest -q
git diff --check
```

For broader source checks, run:

```powershell
python main.py --health-check
python main.py --release-check
```

## Safety Boundary

Jarvis v0.2.0 is a controlled assistant checkpoint:

- It does not execute arbitrary shell commands through assistant prompts.
- It does not click, type, or automate the desktop.
- It does not browse arbitrary URLs.
- It does not read file contents unless file-read settings and confirmation allow it.
- It does not upload screenshots or files to OpenAI without explicit enablement and confirmation.
- It does not send email directly except the explicit draft-send workflow with OAuth, scopes, permission checks, and confirmation.
- It does not run as a Windows service or require admin permissions for startup registration.

## Project Layout

```text
Jarvis/
  main.py
  app/
  assistant/
  agent/
  config/
  diagnostics/
  docs/
  gui/
  integrations/
  memory/
  reminders/
  services/
  tools/
  vision/
  voice/
  tests/
```
