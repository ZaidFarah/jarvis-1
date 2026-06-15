# Jarvis

Jarvis is a Windows desktop AI assistant foundation. Phase 1 provides the application shell. Phase 2 adds a safe voice foundation for local microphone diagnostics and provider interfaces only.

The GUI now uses a tabbed dark interface with quick actions for voice, tools, reminders, memory, and diagnostics, plus a tray menu for show, voice loop, reminders, notification test, and exit.

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
- OpenWakeWord dependency support for controlled wake diagnostics.
- `py main.py --openwakeword-test` diagnostic command.
- `py main.py --openwakeword-calibrate` calibration command.
- OpenWakeWord diagnostic logging to `logs/openwakeword.log`.

## Phase 4 Scope

- Wake phrase configuration.
- Wake phrase aliases.
- Fuzzy wake phrase matching with `difflib.SequenceMatcher`.
- Whisper fuzzy wake detection as the default live wake provider.
- OpenWakeWord remains available as an optional diagnostic/configured provider, with Whisper fuzzy fallback.
- Wake detection utility class.
- One-shot `py main.py --wake-test` diagnostic command.
- Wake diagnostic logging to `logs/wake_diagnostics.log`.

## Phase 5 Scope

- Controlled voice command test mode.
- One wake phrase recording.
- One command recording only after wake detection succeeds.
- Command validation rejects empty, punctuation-only, and short filler transcripts before `AssistantCore`.
- Command transcription routed to the existing `AssistantCore` stub only when accepted.
- CLI command: `py main.py --voice-command-test`.
- CLI command: `py main.py --command-capture-test`.
- GUI and tray action: `Voice Command Test`.
- Voice command logs saved to `logs/voice_command_test.log`.
- Command capture diagnostics saved to `logs/command_capture.log`.

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
- Voice command test sends only accepted cleaned commands through `AssistantCore`, so valid commands can use OpenAI or fallback.
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
- Loop flow: sleep, listen for wake phrase, prompt/beep, record one command, transcribe, validate, route accepted commands to `AssistantCore`, speak the response, return to sleep.
- Stop commands: `stop listening`, `sleep jarvis`, `jarvis sleep`, `exit jarvis`, and `shutdown jarvis`.
- Ctrl+C exits the CLI loop cleanly.
- GUI and tray actions: `Start Voice Loop` and `Stop Voice Loop`.
- Voice loop logs are saved to `logs/voice_loop.log`.

## Phase 9.5 Scope

- Wake feedback: `Yes sir?`.
- Rejected command feedback: `I didn’t catch that, please repeat.`
- Return-to-sleep feedback: `Standing by.`
- Voice loop settings: `VOICE_LOOP_ENABLED=false`, `VOICE_LOOP_MAX_EMPTY_COMMANDS=3`, `VOICE_LOOP_WAKE_COOLDOWN_SECONDS=1.5`, `VOICE_LOOP_SPEAK_STATUS=true`.
- Post-speech cooldown before the next listen cycle to reduce self-hearing.
- Empty command limit can stop the loop after repeated silence.
- Stop phrases expanded to include `go to sleep`, `that is all`, and `thank you jarvis`.
- Loop exit summary reports wake attempts, successful wakes, commands handled, empty commands, and errors.
- GUI shows loop status, last recognized command, and last Jarvis response, and disables the loop controls while the loop is active.

## v0.2.0 Phase 6 Scope

- Live voice loop hardening for the full path: sleeping, whisper fuzzy wake detection, command capture, local validation, AssistantCore/OpenAI routing for valid commands, GUI response display, optional TTS, and return to sleep.
- Invalid cleaned commands are rejected locally before `AssistantCore` or OpenAI. This includes empty text, punctuation-only text, `you`, `uh`, `um`, `hmm`, `yeah`, and `okay`.
- Rejected commands trigger exactly `I didn’t catch that, please repeat.`
- The loop retries command capture once. If the retry is valid, the retry text is sent to `AssistantCore`; if it is invalid, Jarvis returns to sleep.
- The GUI transcript and loop fields show rejected commands, retry state, accepted command, assistant response, and sleeping state.

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

## Version

Jarvis uses semantic application versioning from `jarvis_runtime/version.py` and the `APP_VERSION` setting. The current version is `0.1.0`.

Check the source version with:

```powershell
py main.py --version
```

Packaged builds support the same command:

```powershell
dist\Jarvis\Jarvis.exe --version
```

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
WAKE_PROVIDER=whisper_fuzzy
OPENWAKEWORD_ENABLED=false
OPENWAKEWORD_MODEL=hey_jarvis
OPENWAKEWORD_THRESHOLD=0.5
OPENWAKEWORD_LISTEN_CHUNK_MS=80
OPENWAKEWORD_TEST_SECONDS=10
OPENWAKEWORD_FALLBACK_TO_WHISPER=true
```

Detailed wake diagnostics are saved to:

```text
logs/wake_diagnostics.log
```

## OpenWakeWord Test

```powershell
py main.py --openwakeword-test
```

This controlled diagnostic checks the installed `openwakeword` package, lists the built-in models, opens the microphone, listens for a short period, and reports the maximum detection score. OpenWakeWord is currently optional and diagnostic-first; Whisper fuzzy wake detection is the safe default live provider.

If `hey_jarvis` is unavailable in a given environment, choose one of the built-in model names reported by the diagnostic:

- `alexa`
- `hey_jarvis`
- `hey_mycroft`
- `hey_rhasspy`
- `timer`
- `weather`

The diagnostic reports the resolved model path when available. On this local install, the model resolved inside the OpenWakeWord package resource tree. To use a custom wake model, point `OPENWAKEWORD_MODEL` at a local `.onnx` or `.tflite` file path.

## OpenWakeWord Calibration

```powershell
py main.py --openwakeword-calibrate
```

Calibration runs multiple rounds and asks you to say "Hey Jarvis" several times. It reports the maximum score for each round, the average and peak scores across all rounds, the average and max microphone RMS levels, whether the VAD threshold was crossed, and a recommended threshold based on the observed scores.

Calibration settings:

```dotenv
OPENWAKEWORD_CALIBRATION_ROUNDS=5
OPENWAKEWORD_CALIBRATION_SECONDS=4
```

Use calibration when the microphone is working but the wake scores are still low. If RMS is low, the microphone input is weak. If RMS looks healthy but the wake scores stay low, the phrase, pronunciation, or model choice may not match well.

## Wake Provider Check

```powershell
py main.py --wake-provider-check
```

This check reports the selected wake provider, whether OpenWakeWord is enabled and installed, whether a model is configured, whether Whisper fallback is enabled, and the effective provider that Jarvis will use. The default selection is `whisper_fuzzy`.

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
11. Validates the cleaned command and rejects bad short transcripts locally.
12. Sends accepted command text to the existing `AssistantCore` stub.
13. Prints the raw command transcript, cleaned command, accepted status, rejection reason when rejected, and placeholder Jarvis response when accepted.

Voice command capture settings:

```dotenv
WAKE_LISTEN_SECONDS=5
VOICE_COMMAND_START_DELAY_SECONDS=1.0
VOICE_COMMAND_RECORD_SECONDS=7
VOICE_COMMAND_MIN_WORDS=2
VOICE_COMMAND_REJECT_PHRASES=you,uh,um,hmm,yeah,okay
VOICE_COMMAND_RETRY_ON_REJECT=true
VOICE_COMMAND_MAX_RETRIES=1
```

If the command transcription is empty, punctuation-only, too short, or one of the configured rejected phrases, Jarvis prints:

```text
I didn’t catch that, please repeat.
```

Detailed voice command logs are saved to:

```text
logs/voice_command_test.log
```

To speak the Jarvis response after a successful command, pass `--speak`:

```powershell
py main.py --voice-command-test --speak
```

## Command Capture Test

```powershell
py main.py --command-capture-test
```

This records one command sample without requiring wake detection. It prints the provider, sample rate, record seconds, average RMS, max RMS, VAD threshold, whether the threshold was crossed, raw transcript, cleaned command, accepted status, rejection reason when rejected, and the diagnostic log path.

Use this when wake detection works but command capture produces bad transcripts such as `You`, `uh`, or punctuation-only text.

Detailed command capture logs are saved to:

```text
logs/command_capture.log
```

## Voice Loop

```powershell
py main.py --voice-loop
```

The voice loop keeps Jarvis running until stopped:

1. Sleeps while waiting for the wake phrase.
2. Uses the selected wake provider.
3. When OpenWakeWord is active, listens in short chunks before any wake transcription.
4. Falls back to Whisper fuzzy wake detection when OpenWakeWord is unavailable.
5. Prompts with `Yes sir?`, optionally beeps, and waits briefly before recording the command.
6. Records one command clip.
7. Cleans and validates the command text.
8. Stops cleanly if the command is `stop listening`, `go to sleep`, `sleep jarvis`, `jarvis sleep`, `exit jarvis`, `shutdown jarvis`, `that is all`, or `thank you jarvis`.
9. Rejects bad short transcripts locally with `I didn’t catch that, please repeat.` and retries command capture once by default.
10. Sends accepted commands to `AssistantCore`.
11. Speaks accepted responses using the configured TTS provider.
12. Speaks `Standing by.` when returning to sleep.
13. Prints a summary on exit with wake attempts, successful wakes, commands handled, empty commands, and errors.

For GUI visibility, the loop emits explicit events for rejected commands, retrying command capture, accepted commands, assistant responses, and return-to-sleep state.

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

## Health Check

```powershell
py main.py --health-check
```

The health check prints one safe snapshot of the current Jarvis configuration: Python and OS version, OpenAI, voice, memory, reminders, weather, notifications, launchers, file access, calendar, Gmail, vision, and agent flags. It reports detected credentials and keys only as `yes` or `no` and never prints the actual secret values. Detailed health logs are saved to:

```text
logs/health.log
```

## Runtime Check

```powershell
py main.py --runtime-check
```

The runtime check reports whether Jarvis is running in source mode or packaged mode and shows the resolved paths for the config root, env file, `logs/`, `data/`, `credentials/`, and `assets/`. It does not print any secrets or tokens.

## Packaging

Build the Windows EXE with:

```powershell
cmd /c build_exe.bat
```

The output lands in:

```text
dist/Jarvis/Jarvis.exe
```

The build stays console-enabled so the EXE can still print diagnostics for `--runtime-check`, `--health-check`, and `--init-config`. No secrets, tokens, logs, local databases, or credential files are packaged. Bundled assets resolve to PyInstaller's internal assets directory.

Print the packaged smoke test plan from source with:

```powershell
py main.py --packaged-smoke-plan
```

## Installer

Jarvis includes an Inno Setup installer script under `installer/JarvisInstaller.iss`. Install Inno Setup 6 first, then build the installer with:

```powershell
cmd /c build_installer.bat
```

The installer output goes to:

```text
installer\output
```

It installs the packaged EXE plus the PyInstaller internal runtime files, creates a Start Menu shortcut, and offers an optional desktop shortcut. It does not bundle `.env`, credentials, tokens, logs, data databases, or any other secret files.

Windows SmartScreen may warn on unsigned installers and unsigned EXEs. Code signing is not enabled yet, so that warning is expected until signing is added later.

## Signing

Jarvis now includes code-signing preparation, but it does not sign the app yet. Run the readiness check with:

```powershell
py main.py --signing-check
```

The check reports whether `signtool.exe` is available, whether a certificate path is configured, whether a timestamp server is configured, and whether the packaged EXE and installer exist. It never prints certificate secrets.

Use `sign_exe.bat` and `sign_installer.bat` later when you have a real code-signing certificate. A code-signing certificate is a trusted certificate authority certificate that lets Windows verify who published the file. It helps reduce SmartScreen warnings, but it is optional for this phase.

Signing settings:

```dotenv
SIGNING_ENABLED=false
SIGNING_CERT_PATH=
SIGNING_TIMESTAMP_URL=http://timestamp.digicert.com
SIGNING_DESCRIPTION=Jarvis Desktop AI Assistant
```

This phase does not create certificates, does not store certificate passwords, and does not sign the EXE or installer yet.

## Packaged Config

Initialize the external packaged config location with:

```powershell
dist\Jarvis\Jarvis.exe --init-config
```

The same bootstrap can be run from source for testing:

```powershell
py main.py --init-config
```

`--init-config` creates the external config folders and copies `.env.example` to the packaged env file only when that env file is missing. It never overwrites an existing env file and never creates API keys, OAuth tokens, client secrets, or credential JSON files.

Packaged Jarvis uses:

```text
%APPDATA%\Jarvis.env
%APPDATA%\Jarvis\logs
%APPDATA%\Jarvis\data
%APPDATA%\Jarvis\credentials
```

Put API keys in `%APPDATA%\Jarvis.env`. Put Google client secret JSON files in `%APPDATA%\Jarvis\credentials` only when enabling Gmail or Calendar features. Logs and local databases live under `%APPDATA%\Jarvis\logs` and `%APPDATA%\Jarvis\data`.

## Packaged Run

Run the packaged app normally with:

```powershell
run_jarvis.bat
```

Run it in the current console for debugging with:

```powershell
run_jarvis_console.bat
```

Both scripts expect the build output at `dist\Jarvis\Jarvis.exe`.

## Settings

Open the safe settings editor from the GUI `Settings` button or the tray `Settings` action.

The editor only shows common non-secret options:

- wake phrase
- wake match threshold
- voice loop enabled
- TTS provider
- OpenAI TTS voice
- default weather city
- reminders enabled
- notifications enabled
- app launcher enabled
- website launcher enabled
- file access enabled
- agent enabled
- vision enabled

Saving writes only those safe keys to the external `.env` file and leaves unrelated keys alone. Secrets stay hidden. Review the current safe settings and redacted secret settings with:

```powershell
py main.py --settings-check
```

## Log Viewer

Open the safe log viewer from the GUI `Log Viewer` button or the tray `Log Viewer` action.

The viewer only reads files inside the configured logs directory, shows the available log files, and tails the last lines of a selected file. It never deletes logs and redacts obvious secret patterns such as API keys, bearer tokens, OAuth tokens, and client secrets.

List available logs from the CLI with:

```powershell
py main.py --logs-list
```

Tail a specific log with:

```powershell
py main.py --logs-tail jarvis.log --lines 100
```

## Backups

Create a local backup from the GUI `Create Backup` button or the tray `Create Backup` action. Use `List Backups` to see existing local archives. Restore is available only from the CLI for now because it is high risk and must print the restore plan before confirmation.

Create a backup with:

```powershell
py main.py --backup-create
```

List local backups with:

```powershell
py main.py --backup-list
```

Restore a backup with:

```powershell
py main.py --backup-restore backups\Jarvis-0.1.0-YYYYMMDD_HHMMSS.zip
```

Backups live under `backups/` and include the current `.env` file, `data/*.db`, and a backup metadata README. Tokens and the Google client secret stay out of backups unless the corresponding `BACKUP_INCLUDE_*` flag is turned on. Logs, build output, release output, and the Git tree are never included.

## Packaged Smoke Test

After building and initializing config, run:

```powershell
test_packaged_app.bat
```

The smoke test runs:

```text
dist\Jarvis\Jarvis.exe --runtime-check
dist\Jarvis\Jarvis.exe --health-check
dist\Jarvis\Jarvis.exe --openai-check
```

It does not run microphone tests by default. To explicitly include the controlled voice command test, run:

```powershell
test_packaged_app.bat --voice-command-test
```

## Release Check

Run the release readiness check before preparing a manual ZIP:

```powershell
py main.py --release-check
```

The check prints `PASS`, `WARN`, or `FAIL` for release-critical items and ends with a final readiness status. A missing `dist\Jarvis\Jarvis.exe` is a warning so the check can run before a build; tracked secrets or generated local files are failures.

## Final Report

Generate the final local validation report for Jarvis v0.1.0 with:

```powershell
py main.py --final-report
```

The report is written to `reports\Jarvis-0.1.0-validation-report.md` and includes build, release ZIP, runtime, health, release, installer, signing, feature, and security summaries. It never prints secret values.

## Release Notes

Print the v0.1.0 release notes with:

```powershell
py main.py --release-notes
```

The source notes live at `releases\RELEASE_NOTES_0.1.0.md`. The changelog lives at `CHANGELOG.md`.

Tag the checkpoint manually when you are ready:

```powershell
git tag -a v0.1.0 -m "Jarvis v0.1.0"
git push origin v0.1.0
```

Before calling the checkpoint done, run:

```powershell
git status
py -m pytest
py main.py --release-check
py main.py --final-report
```

Release checklist:

1. Run `py -m pytest`.
2. Run `cmd /c build_exe.bat`.
3. Run `dist\Jarvis\Jarvis.exe --version`.
4. Run `dist\Jarvis\Jarvis.exe --init-config`.
5. Run `test_packaged_app.bat`.
6. Run `py main.py --release-check`.
7. Run `py main.py --release-package-check`.
8. Confirm the readiness statuses are `PASS`.

Do not commit or include these in a release ZIP:

```text
.env
credentials/
tokens
logs/
data/*.db
build/
dist/
*.spec
```

Check the release package plan:

```powershell
py main.py --release-package-check
```

Create the versioned ZIP after the build and smoke tests pass:

```powershell
create_release_zip.bat
```

The output is:

```text
releases\Jarvis-0.1.0-windows.zip
```

The ZIP contains `dist\Jarvis\Jarvis.exe`, PyInstaller `_internal` runtime files under `dist\Jarvis`, `README.md`, `run_jarvis.bat`, `run_jarvis_console.bat`, and `test_packaged_app.bat`. Do not add `%APPDATA%\Jarvis.env`, `%APPDATA%\Jarvis\credentials`, logs, local databases, OAuth tokens, API keys, `.git`, installers, updaters, or signing artifacts.

## Windows Startup

Jarvis can optionally register itself to start for the current Windows user. Startup uses only this registry key:

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
```

It does not use admin permissions, `HKLM`, Task Scheduler, Windows services, installers, or elevation. Enable and disable are medium-risk actions, so both require the permission broker and an explicit confirmation.

Check startup status from source:

```powershell
py main.py --startup-check
```

Check startup status from a packaged build:

```powershell
dist\Jarvis\Jarvis.exe --startup-check
```

Enable or disable startup:

```powershell
py main.py --startup-enable
py main.py --startup-disable
```

In source mode, startup targets `run_jarvis.bat` when that launcher exists in the project root. In packaged mode, startup targets the known `Jarvis.exe` path. The GUI Diagnostics tab also includes `Startup Check`, `Enable Startup`, and `Disable Startup` buttons.

Startup settings:

```dotenv
STARTUP_ENABLED=false
STARTUP_APP_NAME=Jarvis
```

Startup diagnostics are written to `logs/startup.log`. Confirmation decisions are written to `logs/confirmations.log`.

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

## Phase 28 Scope

- Gmail draft creation only, no sending.
- Enable draft mode with `GMAIL_DRAFT_ENABLED=true`.
- Draft scope: `GMAIL_DRAFT_SCOPES=https://www.googleapis.com/auth/gmail.compose`.
- Run `py main.py --gmail-draft "recipient@example.com" "Subject" "Body text"` to create a draft after confirmation.
- Assistant commands: `draft email to <email> subject <subject> body <body>` and `create email draft to <email> subject <subject> body <body>`.
- Gmail drafts are high risk and require permission plus confirmation.
- If the token only has the Gmail read-only scope, Jarvis reports: `Gmail compose scope is required. Re-run Gmail auth after enabling draft.`
- Gmail logs are saved to `logs/gmail.log`.

## Phase 29 Scope

- Gmail draft listing and draft sending by draft ID only.
- Enable send-draft mode with `GMAIL_SEND_DRAFT_ENABLED=true`.
- Send scope: `GMAIL_SEND_SCOPES=https://www.googleapis.com/auth/gmail.modify`.
- Run `py main.py --gmail-drafts` to list draft metadata after confirmation.
- Run `py main.py --gmail-send-draft draft-id` to send a saved draft after confirmation.
- Assistant commands: `list email drafts`, `show email drafts`, and `send email draft <draft_id>`.
- Gmail draft listing and draft sending are high risk and require permission plus confirmation.
- If the token only has Gmail read-only scope, Jarvis reports: `Gmail send scope is required. Re-run Gmail auth after enabling send draft.`
- Gmail logs are saved to `logs/gmail.log`.

## Phase 30 Scope

- Vision foundation for manual screenshot capture and OCR diagnostics only.
- Enable with `VISION_ENABLED=true`, `SCREENSHOT_ENABLED=true`, and `OCR_ENABLED=true`.
- Screenshot tests save only under `SCREENSHOT_SAVE_DIR=logs/screenshots`.
- OCR provider: `OCR_PROVIDER=tesseract`.
- OCR output is capped by `OCR_MAX_OUTPUT_CHARS=4000`.
- Run `py main.py --vision-check` to inspect screenshot/OCR readiness.
- Run `py main.py --screenshot-test` to capture a screenshot after confirmation.
- Run `py main.py --ocr-test "<image_path>"` to OCR a local image after confirmation.
- Assistant commands: `take screenshot` and `read screen text`.
- Screenshot capture and OCR are high risk and require permission plus confirmation.
- Jarvis does not send screenshots or OCR text to OpenAI, and it does not click or type on the screen.
- Vision logs are saved to `logs/vision.log`.

## Phase 31 Scope

- OpenAI vision analysis for screenshots and local images only after confirmation.
- Enable with `OPENAI_VISION_ENABLED=true`.
- OpenAI vision model: `OPENAI_VISION_MODEL=gpt-4o-mini`.
- Maximum image size: `OPENAI_VISION_MAX_IMAGE_BYTES=5000000`.
- Run `py main.py --vision-analyze "<image_path>"` to analyze a whitelisted screenshot or test image after confirmation.
- Assistant commands: `analyze screenshot`, `what is on my screen`, and `describe screen`.
- Screenshot capture and image upload to OpenAI are both high risk and each require confirmation.
- Jarvis blocks obvious password, banking, and secret screens before upload.
- Jarvis does not click, type, or control the screen.
- Vision analysis logs are saved to `logs/vision.log`, `logs/chat.log`, and `logs/confirmations.log`.

## Phase 33 Scope

- Experimental LangGraph-style agent runtime that sits beside `AssistantCore`.
- Additions are limited to request classification and dispatch; existing command routing remains the source of truth for permissions and confirmations.
- Run `py main.py --agent-test "what is the weather"` to inspect routing.
- The agent still routes through the existing weather, reminders, app launcher, website launcher, file access, calendar, Gmail, and vision paths.
- It does not add autonomous behavior, background execution, self-modifying logic, desktop automation, browser automation, or code execution.

## Phase 34 Scope

- Optional agent execution path controlled by `AGENT_ENABLED=false`.
- `AssistantCore` keeps the existing direct path unless the agent toggle is enabled.
- Run `py main.py --agent-chat-test "what is the weather"` to exercise the optional agent path through the normal assistant entry point.
- The voice loop uses the agent path automatically when the toggle is enabled.
- The GUI shows whether the agent path is enabled and includes an `Agent Test` action.

## Phase 40 Scope

- Optional Windows startup registration through the current-user Run registry key only.
- CLI commands: `py main.py --startup-check`, `py main.py --startup-enable`, and `py main.py --startup-disable`.
- Startup settings: `STARTUP_ENABLED=false` and `STARTUP_APP_NAME=Jarvis`.
- Enable and disable require permission broker approval plus explicit confirmation.
- Source mode targets `run_jarvis.bat` when present; packaged mode targets the known `Jarvis.exe`.
- GUI diagnostics include startup check, enable, and disable controls.
- Startup logs are saved to `logs/startup.log`; confirmation logs are saved to `logs/confirmations.log`.
- Jarvis does not use `HKLM`, Task Scheduler, Windows services, admin permissions, or elevation.

## Phase 42 Scope

- Application versioning through `jarvis_runtime/version.py` and `APP_VERSION=0.1.0`.
- CLI commands: `py main.py --version` and `py main.py --release-package-check`.
- Manual ZIP release creation with `create_release_zip.bat`.
- Release ZIP output: `releases\Jarvis-0.1.0-windows.zip`.
- The ZIP includes the packaged EXE under `dist\Jarvis`, PyInstaller internal runtime files, README, launcher scripts, and packaged smoke test script only.
- The ZIP excludes `.env`, credentials, tokens, logs, local DB files, `.git`, installers, updaters, and signing artifacts.

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

Jarvis still does not include ElevenLabs, Windows services, Task Scheduler startup, `HKLM` startup registration, browser automation, desktop automation, an updater, or autonomous behavior. Code-signing preparation exists, but the app and installer are not signed yet.

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
