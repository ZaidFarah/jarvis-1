# Jarvis Architecture

This document summarizes the v0.3.0 checkpoint architecture. Jarvis is organized around one routing core, explicit settings, local diagnostics, and capability modules that stay behind allowlists, permissions, and confirmations.

## Runtime Flow

`main.py` is the CLI entry point. With no CLI flag it creates `JarvisApplication` from `app/application.py`, loads settings, configures logging, builds `AssistantCore`, and starts the PySide6 GUI.

`AssistantCore` in `assistant/core.py` is the central request router. It handles local commands first, then falls back to OpenAI chat when enabled. The workflow engine routes a fixed set of multi-step local workflows through the same trusted developer tools. The optional agent runtime can sit in front of the same tool routes, but it does not bypass the existing permission and confirmation boundaries.

## Configuration

`config/settings.py` defines the application configuration with Pydantic Settings. Values come from defaults, `.env`, and environment variables. Secrets and OAuth tokens are never committed and should live only in local `.env` or `credentials/`.

Important defaults for the v0.3.0 checkpoint:

- GUI voice engine: fast
- OpenAI: disabled until configured
- memory and reminders: enabled locally
- app, website, folder, and developer tools: whitelisted
- file reads, summaries, Gmail, Calendar, weather, notifications, and TTS: disabled until explicitly enabled
- confirmations: enabled

## Logging And Diagnostics

`services/logging_service.py` configures Loguru and managed append-only diagnostic sinks. Runtime logs are written under `logs/`, which is ignored by Git.

Diagnostics live mostly under `diagnostics/` and expose CLI checks for health, settings, runtime paths, logs, backups, release packaging, installer readiness, signing readiness, OpenWakeWord, wake providers, voice health, final reports, and release notes.

## Voice

The `voice/` package owns the audio and speech stack:

- `audio_diagnostics.py`: microphone discovery and RMS checks.
- `stt.py`: speech-to-text provider factory, including Faster Whisper and OpenAI STT support.
- `stt_benchmark.py`: records one shared WAV sample or consumes an existing WAV, then compares STT providers against that same audio without running arbitrary shell commands.
- `tts.py`: OpenAI TTS and local `pyttsx3` fallback.
- `wake.py`, `wake_provider.py`, `openwakeword.py`, `wake_diagnostics.py`: wake phrase matching, wake provider selection, and diagnostics.
- `command_validation.py`: local rejection of empty, filler, punctuation-only, short, and incomplete commands.
- `speech_repair.py`: transcript repair before validation.
- `command_capture.py`: one-shot command capture diagnostics.
- `voice_command_test.py`: controlled wake-and-command test path.
- `voice_loop.py`: wake-based loop with retry, follow-up listening, status events, optional TTS, and timing diagnostics.
- `fast_voice.py`: low-latency one-command GUI/CLI path with selectable capture modes, VAD progress, speech repair, validation, OpenAI routing, optional streaming text, and optional TTS.

Voice commands are validated before they reach OpenAI. Raw speech is retained for diagnostics, but invalid or low-confidence text is not routed as a command.

## GUI

`gui/main_window.py` implements the PySide6 red HUD:

- frameless red HUD shell with a central animated assistant core
- voice-first controls with only the essential visible actions and a compact command bar
- command examples plus compact status summaries for screen vision, developer state, and workflow state
- tray menu, status states, transcript, and response surfaces
- voice controls for fast voice or legacy voice loop
- raw, cleaned, and interpreted speech diagnostics
- confidence bars, VAD, RMS, wake/provider status, and turn timing
- compact developer panel and workflow panel instead of button-heavy control blocks
- reminders, notification, health, startup, backup, app, website, folder, and screen vision controls exposed through commands and compact summaries

The GUI is presentation and orchestration only. It calls existing services instead of implementing separate backend behavior.

## Memory

Short-term conversation history is held in memory by `assistant/conversation.py` for the current process only.

Long-term memory uses `memory/store.py` and SQLite. It stores explicit user-approved facts and preferences with structured keys, categories, values, and timestamps. It rejects obvious secrets such as API keys, passwords, and payment card data. Relevant memories may be supplied to OpenAI as user-provided factual context, never as instructions.

## Apps, Browser, And Folders

Safe local tools live in `tools/`:

- `app_launcher.py`: whitelisted Windows app resolution and launch.
- `website_launcher.py`: whitelisted website opens and fixed-provider search.
- `browser_control.py`: safe browser/search facade used by assistant routes.
- `folder_control.py`: whitelisted folder opens and recent downloads.
- `file_access.py`: read-only whitelisted folder listing, file search, file reads, and file summaries when enabled.
- `developer_tools.py`: safe developer workflow helpers for local repo status, tests, and project opens.

These tools do not accept raw shell commands. Folder and file operations are constrained by configured allowlists, extensions, byte limits, permission classification, and confirmation where required.

## Screen Vision

`vision/vision_service.py` owns screenshot capture, monitor listing, OCR, and optional OpenAI vision analysis.

The vision path supports:

- multi-monitor listing and targeted capture
- screenshot storage under `data/screenshots/`
- OCR through the configured OCR provider
- resized JPEG OpenAI vision uploads for faster requests
- timeout-aware OpenAI vision fallback with the original screenshot path preserved
- secret-screen checks before upload
- permission and confirmation gates for screenshot capture and image upload

Vision does not click, type, or automate the screen.

## Reminders And Notifications

`reminders/service.py` and `reminders/store.py` manage local SQLite reminders. `reminders/scheduler.py` runs the optional reminder watcher while Jarvis is running.

`services/notification_service.py` provides optional Windows toast notifications when enabled and available. Notifications are a delivery surface only; they do not create a background daemon or startup service.

## Gmail And Calendar

`integrations/gmail_service.py` and `integrations/calendar_service.py` provide optional Google integrations. They are disabled by default and require local OAuth credentials and tokens.

Gmail and Calendar actions are permission-classified and confirmation-gated. Read, draft, send-draft, read-calendar, and create-calendar flows use separate settings and scopes where appropriate.

## Developer Tools

`tools/developer_tools.py` exposes a safe developer service used by terminal assistant commands and the GUI Developer panel.

Supported actions are:

- run all tests with `python -m pytest -q`
- run the whitelisted fast-test subset
- show `git status --short`
- show `git log -1 --oneline --decorate`
- open selected project files and the tests folder
- open the project in VS Code when resolvable

`tools/workflows.py` builds on the same service to run fixed local workflows:

- `start coding session`
- `review today's work`

These workflows are intentionally bounded and remain local-only.

Developer actions are available only when `DEVELOPER_MODE_ENABLED=true`, are time-limited, use explicit argument lists with `shell=False`, and log to `logs/developer.log`.

## Security Boundary

Jarvis v0.3.0 is intentionally bounded:

- no arbitrary assistant-triggered shell commands
- no autonomous desktop or browser automation
- no raw URL opening
- no unrestricted file paths
- no screenshot upload without enablement and confirmation
- no email send path except confirmed draft-send by draft ID
- no Windows service, admin startup, or system-wide registry writes
- no secret logging

Risky local actions flow through `security/permissions.py` and `security/confirmation.py`.

## Tests

The test suite under `tests/` covers settings, routing, voice behavior, GUI state, memory, reminders, integrations, permissions, packaging diagnostics, and release helpers.

Release-prep validation:

```powershell
python -m py_compile main.py
python -m pytest -q
git diff --check
```
