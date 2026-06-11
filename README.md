# Jarvis

Jarvis is a Windows desktop AI assistant foundation. Phase 1 provides the application shell. Phase 2 adds a safe voice foundation for local microphone diagnostics and provider interfaces only.

## Phase 1 Scope

- PySide6 desktop window with a dark floating Jarvis-style interface.
- System tray icon with show and exit actions.
- Manual command input.
- Status states: Sleeping, Listening, Thinking, Speaking, Error.
- Pydantic Settings configuration from `.env`.
- Loguru logging to `logs/jarvis.log`.
- Assistant core stub that returns a safe placeholder response.
- Basic pytest coverage.

## Phase 2 Scope

- Microphone device detection using `sounddevice`.
- Short local microphone stream test with average and max RMS level reporting.
- RMS-based VAD interface for diagnostics only.
- Speech-to-text provider interface only.
- Text-to-speech provider interface.
- Optional local `pyttsx3` placeholder TTS provider.
- `py main.py --audio-check` diagnostic command.
- GUI `Mic Test` button and tray menu action.
- Audio logging through Loguru, including `logs/audio_diagnostics.log`.

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

Use the `Mic Test` button or tray menu action to run a short local microphone test.

## Audio Check

```powershell
py main.py --audio-check
```

The diagnostic prints available input devices, default microphone name, configured sample rate, whether the microphone stream opened, max RMS level, VAD threshold result, suggestions, and whether local `pyttsx3` TTS is available.

Voice diagnostic settings:

```dotenv
VOICE_SAMPLE_RATE=16000
VOICE_RECORD_SECONDS=5
VOICE_VAD_THRESHOLD=0.0015
```

Detailed audio diagnostic logs are saved to:

```text
logs/audio_diagnostics.log
```

## Test

```powershell
py -m pytest
```

## Not Implemented Yet

Jarvis still does not include wake word detection, Faster Whisper, OpenAI calls, memory, Gmail, Calendar, browser automation, desktop automation, file tools, or vision.

## Project Layout

```text
Jarvis/
  main.py
  app/
  assistant/
  config/
  gui/
  voice/
  services/
  docs/
  tests/
  logs/
  assets/
```
