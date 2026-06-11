# Jarvis Architecture

## Purpose

Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 added a limited local voice foundation for microphone diagnostics and provider interfaces. Phase 2.5 improved diagnostic reliability and reporting. Phase 3 added one-shot Faster Whisper transcription testing. Phase 4 added controlled wake phrase detection as a test mode only. Phase 5 added a controlled one-shot voice command test mode. Phase 6 added OpenAI connection diagnostics. Phase 7 connects `AssistantCore` to OpenAI chat with local fallback. Phase 8 adds safe local text-to-speech for Jarvis responses.

## Phase 1 Components

### Application Bootstrap

`main.py` starts `JarvisApplication` from `app/application.py`. The application object loads settings, configures logging, creates the Qt application, wires the assistant core into the GUI, and handles shutdown.

### Configuration

`config/settings.py` uses Pydantic Settings with the `JARVIS_` environment prefix. Settings may be loaded from `.env`, but Phase 1 does not define or require secrets.

### Logging

`services/logging_service.py` configures Loguru for console logs and `logs/jarvis.log`. Diagnostic logs are written separately for audio, STT, wake, voice command, OpenAI checks, and TTS. Detailed provider, tool, and security audit logging will be added in later approved phases.

### OpenAI Service

`services/openai_service.py` performs safe OpenAI configuration checks and chat requests:

- reports whether OpenAI is enabled
- reports whether an API key exists without printing the key
- reports the selected model
- sends a tiny Responses API request only when enabled and keyed
- writes `logs/openai_diagnostics.log`
- sends chat requests for `AssistantCore`
- writes `logs/chat.log`

OpenAI chat uses the configured `SYSTEM_PROMPT`. The default is: `You are Jarvis, a helpful personal desktop AI assistant.`

### Assistant Core

`assistant/core.py` accepts text commands and routes them to OpenAI when enabled and configured. If OpenAI is disabled, missing a key, or errors, it returns the local placeholder fallback. It does not run tools, access files, or store memory.

### Voice Foundation

`voice/` contains the Phase 2 and 2.5 audio layer:

- `audio_diagnostics.py`: lists microphone devices, runs a short local stream test, writes `logs/audio_diagnostics.log`, and formats readable diagnostic reports.
- `interfaces.py`: defines VAD, speech-to-text, and text-to-speech provider contracts.
- `vad.py`: provides a small RMS-based VAD implementation for diagnostics only.
- `stt.py`: contains the interface-only provider, Faster Whisper provider, and STT provider factory.
- `transcription_diagnostics.py`: records one microphone clip, transcribes it through Faster Whisper, and writes `logs/stt_diagnostics.log`.
- `tts.py`: contains the safe local `pyttsx3` TTS provider, provider factory, TTS result formatting, and `logs/tts.log` sink.
- `wake.py`: detects the configured wake phrase, aliases, and close fuzzy matches using `difflib.SequenceMatcher`.
- `wake_diagnostics.py`: records one microphone clip, transcribes it, runs wake detection, and writes `logs/wake_diagnostics.log`.
- `voice_command_test.py`: records one wake phrase clip, records one command clip only when wake is detected, sends the command transcript to `AssistantCore`, optionally speaks the response, and writes `logs/voice_command_test.log`.

No continuous listening, cloud TTS, or OpenAI voice integration is implemented in Phase 8.

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
- Phase 5: controlled one-shot voice command test
- Phase 6: OpenAI connection diagnostics only
- Phase 7: OpenAI-backed AssistantCore responses with fallback
- Phase 8: safe local pyttsx3 text-to-speech output
- Later voice phase: continuous speech loop
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics

## Safety Boundary

Phase 8 has no tools. It cannot access email, calendar, browser automation, desktop automation, memory, screenshots, or local file content. OpenAI usage is limited to plain text chat responses from the user command text. Text-to-speech is local-only through `pyttsx3`.
