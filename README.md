# Jarvis

Jarvis is a Windows desktop AI assistant foundation. Phase 1 provides the application shell only: configuration, logging, a modern PySide6 floating window, tray support, status states, and a safe assistant stub.

## Phase 1 Scope

- PySide6 desktop window with a dark floating Jarvis-style interface.
- System tray icon with show and exit actions.
- Manual command input.
- Status states: Sleeping, Listening, Thinking, Speaking, Error.
- Pydantic Settings configuration from `.env`.
- Loguru logging to `logs/jarvis.log`.
- Assistant core stub that returns a safe placeholder response.
- Basic pytest coverage.

## Setup

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

Optional local configuration:

```powershell
Copy-Item .env.example .env
```

Do not add API keys in Phase 1. Future provider keys will be added only when the relevant phase is approved.

## Run

```powershell
py main.py
```

Type a command in the input box and press Enter or Send. Jarvis will echo a safe placeholder response until the real assistant runtime is added in a later phase.

## Test

```powershell
py -m pytest
```

## Not Implemented Yet

Phase 1 intentionally does not include voice, wake word detection, OpenAI calls, memory, Gmail, Calendar, browser automation, desktop automation, file tools, or vision.

## Project Layout

```text
Jarvis/
  main.py
  app/
  assistant/
  config/
  gui/
  services/
  docs/
  tests/
  logs/
  assets/
```
