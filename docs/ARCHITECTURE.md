# Jarvis Architecture

## Purpose

Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 creates only the safe foundation: a runnable desktop shell, configuration, logging, an assistant stub, and tests.

## Phase 1 Components

### Application Bootstrap

`main.py` starts `JarvisApplication` from `app/application.py`. The application object loads settings, configures logging, creates the Qt application, wires the assistant core into the GUI, and handles shutdown.

### Configuration

`config/settings.py` uses Pydantic Settings with the `JARVIS_` environment prefix. Settings may be loaded from `.env`, but Phase 1 does not define or require secrets.

### Logging

`services/logging_service.py` configures Loguru for console logs and `logs/jarvis.log`. Detailed provider, tool, and security audit logging will be added in later approved phases.

### Assistant Core

`assistant/core.py` is a stub. It accepts typed text commands and returns a safe placeholder response. It does not call OpenAI, run tools, access files, or store memory.

### GUI

`gui/main_window.py` contains the PySide6 floating Jarvis shell:

- dark frameless window
- animated orb
- system tray icon
- manual command input
- transcript panel
- status states: Sleeping, Listening, Thinking, Speaking, Error

The window can be hidden to the tray and safely exited from the tray menu.

## Future Architecture

Future phases should add capabilities behind explicit approval gates:

- Phase 2: voice input, wake word, speech-to-text, text-to-speech
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics

## Safety Boundary

Phase 1 has no risky tools. It cannot access email, calendar, browser automation, desktop automation, memory, OpenAI, microphone, screenshots, or local file content. The assistant is intentionally limited to a local placeholder response.
