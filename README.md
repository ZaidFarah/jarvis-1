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

## Phase 10 Scope

- In-memory short-term conversation history for the current session only.
- Conversation history keeps the last `CONVERSATION_HISTORY_MAX_MESSAGES` messages.
- Chat and voice loop requests send recent history to OpenAI when history is enabled.
- CLI command: `py main.py --chat-session`.
- Session exit commands: `exit`, `quit`, and `bye`.
- `reset conversation` clears only the current short-term history.
- Conversation history is not written to disk.

## Phase 11 Scope

- SQLite-only persistent local memory.
- Explicit memory commands only: `remember that ...`, `forget that ...`, `what do you remember`, and `reset memory`.
- Memory settings: `MEMORY_ENABLED=true`, `MEMORY_DATABASE_PATH=data/jarvis_memory.db`.
- Only user-approved facts are stored.
- Sensitive secrets such as API keys, passwords, and payment card details are rejected.
- Memory persists across restarts because it is stored in SQLite.

## Phase 12 Scope

- Safe weather integration through OpenWeatherMap only.
- CLI command: `py main.py --weather-check`.
- Assistant weather prompts: `what is the weather`, `weather today`, and `what is the weather in <city>`.
- Weather settings: `WEATHER_ENABLED=false`, `WEATHER_PROVIDER=openweathermap`, `WEATHER_API_KEY=`, `WEATHER_DEFAULT_CITY=Nottingham`, `WEATHER_UNITS=metric`.
- Weather requests are skipped safely when disabled or missing a key.
- Weather logs are saved to `logs/weather.log`.

## Phase 13 Scope

- Local reminders backed by SQLite.
- Reminder commands: `remind me to <task>`, `remind me to <task> at <time>`, `list reminders`, `show reminders`, `cancel reminder <id>`, and `complete reminder <id>`.
- Reminder time parsing stays simple and expects `YYYY-MM-DD HH:MM` or a close ISO-like equivalent.
- CLI command: `py main.py --reminders-test`.
- Reminder settings: `REMINDERS_ENABLED=true`, `REMINDERS_DATABASE_PATH=data/jarvis_reminders.db`.
- Reminder logs are saved to `logs/reminders.log`.

## Phase 14 Scope

- Manual reminder checking for due reminders.
- Reminder commands: `due reminders` and `check reminders`.
- CLI command: `py main.py --reminders-check`.
- Optional spoken reminder output with `--speak`.
- Reminder check settings: `REMINDERS_CHECK_ENABLED=true`, `REMINDERS_CHECK_INTERVAL_SECONDS=60`, `REMINDERS_SPEAK_DUE=false`.
- The GUI includes a `Check Reminders` control and shows the last reminder check result.

## Phase 15 Scope

- Local reminder watcher that runs only while Jarvis is running.
- CLI command: `py main.py --reminders-watch`.
- Optional spoken watcher output with `--reminders-watch --speak`.
- Watch settings: `REMINDERS_WATCH_ENABLED=false`, `REMINDERS_WATCH_SPEAK=false`.
- The GUI includes `Start Watch` and `Stop Watch` controls and shows watcher status.

## Phase 16 Scope

- Optional Windows toast notifications through `winotify` when available.
- CLI commands: `py main.py --notification-check` and `py main.py --notification-test "Hello from Jarvis"`.
- Reminder checks and the reminder watcher can optionally emit toast notifications when `REMINDERS_TOAST_ENABLED=true`.
- Notification settings: `NOTIFICATIONS_ENABLED=false`, `NOTIFICATION_PROVIDER=windows_toast`, `REMINDERS_TOAST_ENABLED=false`.
- Notification logs are saved to `logs/notifications.log`.

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

## Chat Session

```powershell
py main.py --chat-session
```

The chat session keeps a single in-memory conversation open across turns. It reuses the current short-term history so follow-up questions can reference earlier turns in the same session. Type `reset conversation` to clear only the current history, or `exit`, `quit`, or `bye` to end the session.

## Memory Test

```powershell
py main.py --memory-test
```

The memory test uses an isolated SQLite database and exercises remember, list, forget, and reset flows without touching the main memory database.

## Weather Check

```powershell
py main.py --weather-check
```

The weather check reports whether weather is enabled, which provider is selected, whether an API key is present, the default city, and whether a live request was attempted. If weather is enabled and the key exists, Jarvis requests current weather from OpenWeatherMap. The command never prints the API key.

## Reminders Test

```powershell
py main.py --reminders-test
```

The reminders test uses an isolated SQLite database and exercises reminder creation, listing, completion, and cancellation without touching the main reminders database.

## Reminders Check

```powershell
py main.py --reminders-check
```

Jarvis checks for reminders where `remind_at` is due and `status` is still pending. Matching reminders are marked `notified` after they are reported, so they are not repeated on the next check. Pass `--speak` to speak the result aloud.

## Reminders Watch

```powershell
py main.py --reminders-watch
```

The reminder watcher checks due reminders every `REMINDERS_CHECK_INTERVAL_SECONDS` while Jarvis is running. It stops cleanly when you press Ctrl+C or close the GUI. Pass `--speak` to have due reminders spoken aloud.

## Notification Check

```powershell
py main.py --notification-check
```

The notification check reports whether Windows toast notifications are enabled, which provider is selected, whether the provider is available, and whether a diagnostic toast was delivered. It never prints secrets.

## Notification Test

```powershell
py main.py --notification-test "Hello from Jarvis"
```

The notification test sends a one-off toast using the configured provider when notifications are enabled and the provider is available. On unsupported platforms or when the provider cannot load, Jarvis fails safely and reports the reason.

## Phase 17 Scope

- Safe local application launcher for whitelisted commands only.
- CLI commands: `py main.py --app-launcher-check`, `py main.py --resolve-app notepad`, and `py main.py --launch-app notepad`.
- Assistant commands: `open notepad`, `launch calculator`, `open edge`, `open vscode`, and `open docker`.
- Launcher settings: `APP_LAUNCHER_ENABLED=true`, `APP_LAUNCHER_ALLOWED_APPS=notepad=notepad.exe,calculator=calc.exe,chrome=,edge=,vscode=,docker=`.
- Launcher logs are saved to `logs/app_launcher.log`.

## App Launcher Check

```powershell
py main.py --app-launcher-check
```

The app launcher check prints whether the launcher is enabled, whether the platform is supported, and which apps are allowed. It never executes arbitrary commands.

## Resolve App

```powershell
py main.py --resolve-app notepad
```

Jarvis resolves the whitelisted app to a concrete executable path or reports that the app cannot be resolved. It does not launch the app.

## Launch App

```powershell
py main.py --launch-app notepad
```

Jarvis can launch only apps listed in `APP_LAUNCHER_ALLOWED_APPS`. If an app is missing or not configured, Jarvis refuses the request.

## Website Check

```powershell
py main.py --website-check
```

The website check reports whether website launching is enabled and which sites are allowed. It never opens a page.

## Open Site

```powershell
py main.py --open-site google
```

Jarvis can open only sites listed in `WEBSITE_ALLOWED_SITES`. If a site is missing or not configured, Jarvis refuses the request. Raw URLs are rejected.

## Phase 18 Scope

- Safe website launcher for whitelisted sites only.
- CLI commands: `py main.py --website-check` and `py main.py --open-site google`.
- Assistant commands: `open google`, `open youtube`, `open github`, `open gmail`, `open outlook`, and `open blackboard`.
- Website settings: `WEBSITE_LAUNCHER_ENABLED=true`, `WEBSITE_ALLOWED_SITES=google=https://www.google.com,youtube=https://www.youtube.com,github=https://github.com,gmail=https://mail.google.com,blackboard=,outlook=https://outlook.office.com`.
- Raw URLs are rejected and sites without configured URLs fail safely.
- Website logs are saved to `logs/website_launcher.log`.

## Phase 19 Scope

- Safe read-only file access for whitelisted folders only.
- CLI commands: `py main.py --file-access-check`, `py main.py --list-folder documents`, and `py main.py --find-file "example" documents`.
- Assistant commands: `list documents`, `list desktop`, `list downloads`, `find file <name> in documents`, `find file <name> in desktop`, and `find file <name> in downloads`.
- File access settings: `FILE_ACCESS_ENABLED=false`, `FILE_ACCESS_ALLOWED_FOLDERS=documents=%USERPROFILE%\Documents,desktop=%USERPROFILE%\Desktop,downloads=%USERPROFILE%\Downloads`.
- File access is read-only and lists filenames plus metadata only.
- Absolute paths and traversal attempts are rejected.
- File access logs are saved to `logs/file_access.log`.

## Phase 20 Scope

- Central permission broker for classifying sensitive actions.
- CLI commands: `py main.py --permission-check` and `py main.py --permission-check-action "delete files"`.
- Default policies cover low, medium, high, and blocked risk levels.
- Existing low-risk actions are logged but not blocked yet.
- Permission logs are saved to `logs/permissions.log`.

## Phase 21 Scope

- Confirmation layer for medium and high risk actions.
- CLI command: `py main.py --confirm-test "read file contents"`.
- GUI modal confirmation dialog with approve and deny buttons.
- Confirmation settings: `CONFIRMATION_REQUIRED=true`, `CONFIRMATION_TIMEOUT_SECONDS=30`.
- Confirmation prompts fail closed on timeout.
- Confirmation logs are saved to `logs/confirmations.log`.

## Phase 22 Scope

- Safe read-only file content reading for whitelisted folders only.
- CLI command: `py main.py --read-file "example.txt" documents`.
- Assistant command: `read file <filename> in documents|desktop|downloads`.
- File read settings: `FILE_READ_ENABLED=false`, `FILE_READ_MAX_BYTES=20000`, `FILE_READ_MAX_OUTPUT_CHARS=4000`, `FILE_READ_ALLOWED_EXTENSIONS=.txt,.md,.csv,.json,.py,.java,.cpp,.h,.html,.css,.js`.
- Reading file contents is medium risk and goes through the permission broker plus confirmation flow.
- Binary files, raw paths, traversal attempts, unknown folders, and disallowed extensions are rejected.
- File content reads are not sent to OpenAI automatically.
- File access logs are saved to `logs/file_access.log`.
- Confirmation logs are saved to `logs/confirmations.log`.

## Phase 23 Scope

- Safe file summarization for whitelisted text files only.
- CLI command: `py main.py --summarize-file "example.txt" documents`.
- Assistant command: `summarize file <filename> in documents|desktop|downloads`.
- File summary settings: `FILE_SUMMARY_ENABLED=false`, `FILE_SUMMARY_MAX_CHARS=6000`.
- Summaries require confirmation before reading file content and again before sending content to OpenAI.
- Summaries are blocked for binary files, traversal, absolute paths, unknown folders, and disallowed extensions.
- File content is not stored in short-term memory or long-term memory.
- File access logs are saved to `logs/file_access.log`.
- Chat logs are saved to `logs/chat.log`.
- Confirmation logs are saved to `logs/confirmations.log`.

## Phase 24 Scope

- Safe Google Calendar read-only foundation.
- CLI command: `py main.py --calendar-check`.
- Assistant commands: `what is on my calendar today`, `show my calendar today`, `what events do i have today`, and `what is on my calendar tomorrow`.
- Calendar settings: `CALENDAR_ENABLED=false`, `CALENDAR_CLIENT_SECRET_PATH=credentials/google_client_secret.json`, `CALENDAR_TOKEN_PATH=credentials/token_calendar.json`.
- Calendar reads are high risk and require confirmation.
- Calendar diagnostics report enabled state, credential presence, token presence, and authentication status without printing secrets.
- Calendar logs are saved to `logs/calendar.log`.

## Phase 25 Scope

- Google Calendar OAuth setup and read-only event queries.
- Put your OAuth client secret JSON at `credentials/google_client_secret.json`.
- Run `py main.py --calendar-auth` to complete sign-in and save the token at `credentials/token_calendar.json`.
- Run `py main.py --calendar-today` or `py main.py --calendar-tomorrow` to read events after confirmation.
- Calendar scope: `CALENDAR_SCOPES=https://www.googleapis.com/auth/calendar.readonly`.
- Calendar auth never prints the client secret or token.
- Calendar logs are saved to `logs/calendar.log`.
- If the client secret or token is missing, the CLI reports the setup step that is still required.

## Phase 26 Scope

- Google Calendar event creation with strict confirmation.
- Enable creation with `CALENDAR_CREATE_ENABLED=true`.
- Keep read-only scope separate from write scope:
  - `CALENDAR_SCOPES=https://www.googleapis.com/auth/calendar.readonly`
  - `CALENDAR_WRITE_SCOPES=https://www.googleapis.com/auth/calendar.events`
- Run `py main.py --calendar-auth` after enabling creation so Jarvis can request the write scope explicitly.
- Run `py main.py --calendar-create "Meeting" "2026-06-12 18:30" 30` to create a calendar event after confirmation.
- Assistant commands: `create calendar event <title> at <YYYY-MM-DD HH:MM> for <minutes>` and `schedule <title> at <YYYY-MM-DD HH:MM> for <minutes>`.
- Calendar creation is high risk and always requires permission plus confirmation.
- If the token only has read-only scope, Jarvis reports: `Calendar write scope is required. Re-run calendar auth after enabling create.`
- Calendar logs are saved to `logs/calendar.log`.

## Phase 27 Scope

- Gmail unread metadata only, with read-only OAuth setup.
- Put your OAuth client secret JSON at `credentials/google_client_secret.json`.
- Run `py main.py --gmail-auth` to complete sign-in and save the token at `credentials/token_gmail.json`.
- Run `py main.py --gmail-unread` to read unread message metadata after confirmation.
- Assistant commands: `read my unread emails`, `show unread emails`, `check my Gmail`, and `check my emails`.
- Gmail scope: `GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly`.
- Gmail reads only sender, subject, snippet, and date when available.
- Gmail logs are saved to `logs/gmail.log`.

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

Jarvis still does not include ElevenLabs, startup background service, LangGraph, browser automation, desktop automation, or vision.

## Project Layout

```text
Jarvis/
  main.py
  app/
  assistant/
  config/
  integrations/
  reminders/
  gui/
  voice/
  services/
  docs/
  tests/
  logs/
  assets/
```
