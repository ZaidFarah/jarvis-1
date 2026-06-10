# Jarvis Architecture

## Purpose

Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 adds a limited local voice foundation for microphone diagnostics and provider interfaces.

## Phase 1 Components

### Application Bootstrap

`main.py` starts `JarvisApplication` from `app/application.py`. The application object loads settings, configures logging, creates the Qt application, wires the assistant core into the GUI, and handles shutdown.

### Configuration

`config/settings.py` uses Pydantic Settings with the `JARVIS_` environment prefix. Settings may be loaded from `.env`, but Phase 1 does not define or require secrets.

### Logging

`services/logging_service.py` configures Loguru for console logs and `logs/jarvis.log`. Detailed provider, tool, and security audit logging will be added in later approved phases.

### Assistant Core

`assistant/core.py` is a stub. It accepts typed text commands and returns a safe placeholder response. It does not call OpenAI, run tools, access files, or store memory.

### Voice Foundation

`voice/` contains the Phase 2 audio layer:

- `audio_diagnostics.py`: lists microphone devices and runs a short local stream test.
- `interfaces.py`: defines VAD, speech-to-text, and text-to-speech provider contracts.
- `vad.py`: provides a small RMS-based VAD implementation for diagnostics only.
- `stt.py`: contains an interface-only placeholder STT provider.
- `tts.py`: contains an optional local `pyttsx3` TTS provider.

No wake word, continuous listening, Faster Whisper, cloud TTS, or OpenAI voice integration is implemented in Phase 2.

### GUI

`gui/main_window.py` contains the PySide6 floating Jarvis shell:

- dark frameless window
- animated orb
- system tray icon
- manual command input
- microphone test button
- transcript panel
- status states: Sleeping, Listening, Thinking, Speaking, Error

The window can be hidden to the tray and safely exited from the tray menu.

## Future Architecture

Future phases should add capabilities behind explicit approval gates:

- Phase 2: microphone diagnostics and voice provider interfaces
- Later voice phase: wake word, speech-to-text, text-to-speech loop
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics

## Safety Boundary

Phase 2 has no risky tools. It cannot access email, calendar, browser automation, desktop automation, memory, OpenAI, screenshots, or local file content. The microphone path is limited to local device detection and a short user-triggered test.
