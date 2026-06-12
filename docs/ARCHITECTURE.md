# Jarvis Architecture

## Purpose

Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 added a limited local voice foundation for microphone diagnostics and provider interfaces. Phase 2.5 improved diagnostic reliability and reporting. Phase 3 added one-shot Faster Whisper transcription testing. Phase 4 added controlled wake phrase detection as a test mode only. Phase 5 added a controlled one-shot voice command test mode. Phase 6 added OpenAI connection diagnostics. Phase 7 connects `AssistantCore` to OpenAI chat with local fallback. Phase 8 adds safe local text-to-speech for Jarvis responses. Phase 8.5 adds OpenAI TTS as the preferred voice provider with local `pyttsx3` fallback. Phase 8.6 improves one-shot command capture timing after wake detection. Phase 9 adds the first continuous voice loop. Phase 9.5 polishes that loop with spoken status feedback, cooldowns, summary counters, and richer GUI state. Phase 10 adds short-term in-memory conversation history for the current session.

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
- `tts.py`: contains the OpenAI TTS provider, safe local `pyttsx3` fallback, provider factory, generated audio playback, TTS result formatting, `logs/audio/` output, and `logs/tts.log` sink.
- `wake.py`: detects the configured wake phrase, aliases, and close fuzzy matches using `difflib.SequenceMatcher`.
- `wake_diagnostics.py`: records one microphone clip, transcribes it, runs wake detection, and writes `logs/wake_diagnostics.log`.
- `voice_command_test.py`: records one wake phrase clip, waits briefly after wake detection, optionally plays a Windows beep, records one command clip using the command duration setting, treats punctuation-only command transcripts as empty, sends valid command text to `AssistantCore`, optionally speaks the response, and writes `logs/voice_command_test.log`.
- `voice_loop.py`: runs the continuous one-command-at-a-time voice loop, handles stop commands, speaks accepted assistant responses, applies post-speech cooldowns, reports summary counters, and writes `logs/voice_loop.log`.
- `conversation.py`: keeps short-term in-memory conversation turns, trims to the configured maximum, and formats recent history for prompts.

No ElevenLabs, voice cloning, real-time OpenAI voice conversation, permissions system, startup background service, or tool execution is implemented in Phase 9.

### GUI

`gui/main_window.py` contains the PySide6 floating Jarvis shell:

- dark frameless window
- animated orb
- system tray icon
- manual command input
- microphone test button
- start and stop voice loop controls
- current loop status, last command, and last response fields
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
- Phase 8.5: OpenAI text-to-speech output with pyttsx3 fallback
- Phase 8.6: clearer one-shot command capture timing after wake detection
- Phase 9: first continuous one-command-at-a-time voice loop
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics

## Safety Boundary

Phase 9 has no tools, no startup background service, and no permissions system. It cannot access email, calendar, browser automation, desktop automation, memory, screenshots, or local file content. OpenAI usage is limited to plain text chat responses and text-to-speech from the user command text or assistant response. The OpenAI TTS voice direction is an original assistant voice: calm, mature, professional, British-inspired, deep but clear, slightly cinematic, and natural paced. It must not clone or imitate a real actor or copyrighted movie character.

Phase 10 adds only in-memory conversation context. It does not persist history to disk or add long-term memory, databases, or retrieval systems.
