# Jarvis Architecture

## Purpose

Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 added a limited local voice foundation for microphone diagnostics and provider interfaces. Phase 2.5 improved diagnostic reliability and reporting. Phase 3 added one-shot Faster Whisper transcription testing. Phase 4 adds controlled wake phrase detection as a test mode only.

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

`voice/` contains the Phase 2 and 2.5 audio layer:

- `audio_diagnostics.py`: lists microphone devices, runs a short local stream test, writes `logs/audio_diagnostics.log`, and formats readable diagnostic reports.
- `interfaces.py`: defines VAD, speech-to-text, and text-to-speech provider contracts.
- `vad.py`: provides a small RMS-based VAD implementation for diagnostics only.
- `stt.py`: contains the interface-only provider, Faster Whisper provider, and STT provider factory.
- `transcription_diagnostics.py`: records one microphone clip, transcribes it through Faster Whisper, and writes `logs/stt_diagnostics.log`.
- `tts.py`: contains an optional local `pyttsx3` TTS provider.
- `wake.py`: detects the configured wake phrase, aliases, and close fuzzy matches using `difflib.SequenceMatcher`.
- `wake_diagnostics.py`: records one microphone clip, transcribes it, runs wake detection, and writes `logs/wake_diagnostics.log`.

No continuous listening, cloud TTS, or OpenAI voice integration is implemented in Phase 4.

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
- Phase 2.5: clearer diagnostics, dedicated audio log, stronger microphone suggestions
- Phase 3: one-shot Faster Whisper speech-to-text diagnostic
- Phase 4: one-shot wake phrase detection diagnostic
- Later voice phase: continuous speech loop
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics

## Safety Boundary

Phase 4 has no risky tools. It cannot access email, calendar, browser automation, desktop automation, memory, OpenAI, screenshots, or local file content. The microphone path is limited to local user-triggered diagnostics, one-shot transcription testing, and one-shot wake phrase testing.
