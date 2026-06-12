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

## Phase 3 Scope

- Faster Whisper dependency support.
- `faster_whisper` speech-to-text provider.
- One-shot transcription diagnostic command.
- Short microphone recording using configured voice settings.
- STT diagnostic logging to `logs/stt_diagnostics.log`.
- Graceful error output if Faster Whisper or the model cannot load.

## Phase 4 Scope

- Wake phrase configuration.
- Wake phrase aliases.
- Fuzzy wake phrase matching with `difflib.SequenceMatcher`.
- Wake detection utility class.
- One-shot `py main.py --wake-test` diagnostic command.
- Wake diagnostic logging to `logs/wake_diagnostics.log`.

## Phase 5 Scope

- Controlled voice command test mode.
- One wake phrase recording.
- One command recording only after wake detection succeeds.
- Command transcription routed to the existing `AssistantCore` stub.
- CLI command: `py main.py --voice-command-test`.
- GUI and tray action: `Voice Command Test`.
- Voice command logs saved to `logs/voice_command_test.log`.

## Phase 6 Scope

- OpenAI dependency support.
- Safe OpenAI configuration diagnostics.
- CLI command: `py main.py --openai-check`.
- Optional small Responses API test request only when OpenAI is enabled and an API key is present.
- OpenAI logs saved to `logs/openai_diagnostics.log`.
- OpenAI is not connected to `AssistantCore` yet.

## Phase 7 Scope

- `AssistantCore` routes commands to OpenAI when enabled and configured.
- The local placeholder remains as fallback when OpenAI is disabled, missing a key, or errors.
- CLI command: `py main.py --chat-test`.
- Voice command test sends the cleaned command through `AssistantCore`, so it can use OpenAI or fallback.
- Chat logs are saved to `logs/chat.log`.

## Phase 8 Scope

- Safe local text-to-speech through `pyttsx3`.
- TTS is disabled by default unless `TTS_ENABLED=true` or a CLI command explicitly uses `--speak`.
- CLI command: `py main.py --tts-test "Hello, I am Jarvis."`.
- Chat and voice command tests can speak responses with `--speak`.
- TTS logs are saved to `logs/tts.log`.

## Phase 8.5 Scope

- OpenAI TTS is the preferred provider with `pyttsx3` fallback.
- Generated OpenAI speech audio is stored temporarily under `logs/audio/`.
- CLI command: `py main.py --tts-test "Hello sir, Jarvis is online." --provider openai`.
- Chat and voice command speech uses OpenAI TTS when `TTS_PROVIDER=openai`.
- The configured voice direction is original: mature, calm, confident, professional, British-inspired, deep but clear, slightly cinematic, natural paced, and not an imitation of a real actor or copyrighted movie character.

## Phase 8.6 Scope

- Voice command capture waits briefly after wake detection before recording the command.
- Wake listening and command recording durations are configured separately.
- CLI voice command test prints a clear prompt before command recording.
- Windows may play a short local beep before command recording; beep failures are ignored.
- Punctuation-only command transcriptions are treated as empty and reported cleanly.

## Phase 9 Scope

- Continuous one-command-at-a-time voice loop.
- CLI command: `py main.py --voice-loop`.
- Loop flow: sleep, listen for wake phrase, prompt/beep, record one command, transcribe, route to `AssistantCore`, speak the response, return to sleep.
- Stop commands: `stop listening`, `sleep jarvis`, `jarvis sleep`, `exit jarvis`, and `shutdown jarvis`.
- Ctrl+C exits the CLI loop cleanly.
- GUI and tray actions: `Start Voice Loop` and `Stop Voice Loop`.
- Voice loop logs are saved to `logs/voice_loop.log`.

## Phase 9.5 Scope

- Wake feedback: `Yes sir?`.
- Empty command feedback: `I didn't catch that.`
- Return-to-sleep feedback: `Standing by.`
- Voice loop settings: `VOICE_LOOP_ENABLED=false`, `VOICE_LOOP_MAX_EMPTY_COMMANDS=3`, `VOICE_LOOP_WAKE_COOLDOWN_SECONDS=1.5`, `VOICE_LOOP_SPEAK_STATUS=true`.
- Post-speech cooldown before the next listen cycle to reduce self-hearing.
- Empty command limit can stop the loop after repeated silence.
- Stop phrases expanded to include `go to sleep`, `that is all`, and `thank you jarvis`.
- Loop exit summary reports wake attempts, successful wakes, commands handled, empty commands, and errors.
- GUI shows loop status, last recognized command, and last Jarvis response, and disables the loop controls while the loop is active.

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

## Transcription Test

```powershell
py main.py --transcribe-test
```

The command records one short microphone clip and sends it to Faster Whisper. It prints the provider, model, device, compute type, recording level, VAD result, transcription text, and any errors.

Speech-to-text settings:

```dotenv
STT_PROVIDER=faster_whisper
WHISPER_MODEL=base.en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Detailed STT diagnostics are saved to:

```text
logs/stt_diagnostics.log
```

## Wake Test

```powershell
py main.py --wake-test
```

The command records one short microphone clip, transcribes it with Faster Whisper, and checks whether the transcript matches the configured wake phrase or aliases.

Wake settings:

```dotenv
WAKE_PHRASE=hey jarvis
WAKE_ALIASES=hey jarvis,hi jarvis,wake up jarvis,jarvis wake up,okay jarvis,yo jarvis
WAKE_MATCH_THRESHOLD=0.72
WAKE_LISTEN_SECONDS=5
```

Detailed wake diagnostics are saved to:

```text
logs/wake_diagnostics.log
```

## Voice Command Test

```powershell
py main.py --voice-command-test
```

The command runs one controlled voice command flow:

1. Records a wake phrase clip.
2. Transcribes the wake phrase.
3. Checks the transcript against the wake phrase and aliases.
4. If wake is detected, prints `Yes sir?`
5. Waits for `VOICE_COMMAND_START_DELAY_SECONDS`.
6. Plays a short Windows beep when available.
7. Prints `Listening for command...`.
8. Records one command clip using `VOICE_COMMAND_RECORD_SECONDS`.
9. Transcribes the command.
10. Removes a wake phrase prefix from the command transcript when present.
11. Sends the cleaned command text to the existing `AssistantCore` stub.
12. Prints the raw command transcript, cleaned command, and placeholder Jarvis response.

Voice command capture settings:

```dotenv
WAKE_LISTEN_SECONDS=5
VOICE_COMMAND_START_DELAY_SECONDS=1.0
VOICE_COMMAND_RECORD_SECONDS=7
```

If the command transcription is empty or punctuation-only, Jarvis prints:

```text
I didn't catch that.
```

Detailed voice command logs are saved to:

```text
logs/voice_command_test.log
```

To speak the Jarvis response after a successful command, pass `--speak`:

```powershell
py main.py --voice-command-test --speak
```

## Voice Loop

```powershell
py main.py --voice-loop
```

The voice loop keeps Jarvis running until stopped:

1. Sleeps while waiting for the wake phrase.
2. Records one wake phrase clip.
3. Transcribes and checks the wake phrase.
4. Prompts with `Yes sir?`, optionally beeps, and waits briefly before recording the command.
5. Records one command clip.
6. Cleans the command text.
7. Stops cleanly if the command is `stop listening`, `go to sleep`, `sleep jarvis`, `jarvis sleep`, `exit jarvis`, `shutdown jarvis`, `that is all`, or `thank you jarvis`.
8. Sends valid commands to `AssistantCore`.
9. Speaks accepted responses using the configured TTS provider.
10. Speaks `Standing by.` when returning to sleep.
11. Prints a summary on exit with wake attempts, successful wakes, commands handled, empty commands, and errors.

Press Ctrl+C to stop the CLI loop. Detailed voice loop logs are saved to:

```text
logs/voice_loop.log
```

## OpenAI Check

```powershell
py main.py --openai-check
```

OpenAI settings:

```dotenv
OPENAI_ENABLED=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
SYSTEM_PROMPT=You are Jarvis, a helpful personal desktop AI assistant.
```

The check reports whether OpenAI is enabled, whether an API key is present, the selected model, and whether a test request was attempted. It never prints the API key. A network request is made only when `OPENAI_ENABLED=true` and `OPENAI_API_KEY` is set.

Detailed OpenAI diagnostic logs are saved to:

```text
logs/openai_diagnostics.log
```

## Chat Test

```powershell
py main.py --chat-test
```

You can also pass a message inline:

```powershell
py main.py --chat-test "What can you do?"
```

To print and speak the response:

```powershell
py main.py --chat-test "Say hello as Jarvis" --speak
```

When OpenAI is enabled and an API key exists, Jarvis sends the message to OpenAI with this system prompt:

```text
You are Jarvis, a helpful personal desktop AI assistant.
```

If OpenAI is disabled or unavailable, Jarvis returns the local fallback response. Chat logs are saved to:

```text
logs/chat.log
```

## Text To Speech Test

```powershell
py main.py --tts-test "Hello, I am Jarvis."
```

OpenAI TTS can be selected explicitly:

```powershell
py main.py --tts-test "Hello sir, Jarvis is online." --provider openai
```

Text-to-speech settings:

```dotenv
TTS_ENABLED=false
TTS_PROVIDER=openai
TTS_VOICE_NAME=
TTS_RATE=175
TTS_VOLUME=1.0
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=cedar
OPENAI_TTS_FORMAT=mp3
OPENAI_TTS_INSTRUCTIONS=Speak as a calm, mature, professional British-inspired desktop AI assistant. Use a confident, clear, cinematic tone. Do not sound childish. Keep the pace natural and efficient.
```

OpenAI TTS requires `OPENAI_ENABLED=true` and a configured `OPENAI_API_KEY`. If OpenAI TTS is unavailable or fails, Jarvis falls back to local `pyttsx3`. No API keys are printed. Detailed TTS logs are saved to:

```text
logs/tts.log
```

Generated OpenAI audio files are saved temporarily in:

```text
logs/audio/
```

## Test

```powershell
py -m pytest
```

## Not Implemented Yet

Jarvis still does not include ElevenLabs, startup background service, LangGraph, memory, Gmail, Calendar, browser automation, desktop automation, file tools, permissions system, or vision.

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
