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
- OpenWakeWord is the preferred live wake provider when it is installed and a model is available.
- Whisper fuzzy wake detection remains available as a fallback, but the live loop will switch to manual command mode when OpenWakeWord is unavailable.
- Wake detection utility class.
- One-shot `py main.py --wake-test` diagnostic command.
- Fast `py main.py --wake-debug` and repeated `py main.py --wake-jarvis-test` diagnostics.
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

## GUI

The main window is a premium dark red glassmorphism dashboard with a three-column HUD layout, a large animated circular core, angular control buttons, confidence meters, turn timing, provider indicators, and a compact command bar at the bottom. It uses a Segoe UI Variable-first font stack with Segoe UI fallback, and it is built entirely from PySide6 widgets, gradients, borders, and animations so it remains lightweight on Windows and does not require external artwork.

The GUI `Start Listening` button uses the persistent fast voice engine by default. Each click captures one intentional command and stops automatically. A stronger post-trigger noise gate prevents steady background sound from extending speech indefinitely, while a separate 3-second hard limit bounds noisy captures. It rejects empty audio, weak filler phrases, incomplete prompts such as `tell me`, random number sequences, and low-confidence speech without sending them to OpenAI; the HUD reports `I heard you, but I need a clearer command.` The terminal fast voice loop remains continuous and keeps its existing command validation behavior.

The GUI shows Listening, Transcribing, Thinking, Responding, and Error states and updates the existing HUD panels with raw, cleaned, and repaired speech, response text, transcript confidence, VAD/wake-only state, and timing. The legacy wake-based loop remains available through configuration:

During one-command capture, the HUD updates in real time with VAD waiting/triggered state, detected speech duration, trailing silence, capture percentage, capture completion, transcription readiness, thinking, and response readiness. Speech-to-text remains one-shot.

Fast GUI voice can stream OpenAI text into the response panel as it is generated. The final assembled response still follows the normal AssistantCore path, and unsupported clients fall back to the existing non-streaming request:

```dotenv
FAST_VOICE_STREAM_OPENAI=true
GUI_STREAM_RESPONSE=true
```

Fast GUI voice can speak the completed response after text streaming finishes. TTS is deliberately non-streaming, and the provider card shows whether TTS is off, speaking final responses, or limited to short local acknowledgements. GUI TTS defaults to off. GUI capture uses a 2-second soft limit and extends only while VAD still detects an active question, up to `FAST_VOICE_RECORD_SECONDS`, so longer questions are not cut off:

```dotenv
FAST_VOICE_TTS_MODE=final_response
GUI_FAST_VOICE_MAX_SECONDS=2.0
GUI_FAST_VOICE_HARD_MAX_SECONDS=3.0
GUI_FAST_VOICE_END_SILENCE_MS=350
GUI_FAST_VOICE_NOISE_GATE_MULTIPLIER=1.8
```

Allowed TTS modes are `off`, `final_response`, and `short_ack_only`. When
`FAST_VOICE_TTS_MODE` is unset, the legacy `FAST_VOICE_TTS_ENABLED=true`
setting remains equivalent to `final_response`.

While GUI fast voice is active, the stop control changes to `Stop Listening`
during microphone capture and `Stop Speaking` during TTS. OpenAI TTS playback
and local pyttsx3 playback expose best-effort interruption. A custom provider
without a stop hook cannot be interrupted mid-playback; the HUD reports that
limitation and stops the session after playback returns.

```dotenv
GUI_VOICE_ENGINE=fast
```

Allowed values are `fast` and `legacy`. Start the source GUI with:

```powershell
python main.py
```

Screenshot placeholder note: this repo does not bundle generated screenshots. Add them later under `docs/` or `assets/` only if you want to publish a demo image set.

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

## v0.2.0 Phase 7 Scope

- After a successful assistant response, Jarvis enters one short follow-up listening window before returning to sleep.
- The GUI shows `Listening for follow-up...` during that window.
- Valid follow-up commands are sent to `AssistantCore` and OpenAI without requiring the wake phrase again.
- Invalid non-empty follow-up transcripts are rejected locally with `I didn’t catch that, please repeat.` and retried once.
- If no follow-up is heard, or the retry is still invalid, Jarvis returns to sleep and only speaks `Standing by.` after follow-up mode is finished.
- Whisper fuzzy wake remains the default live wake provider; OpenWakeWord remains optional and diagnostic-first.

## v0.2.0 Phase 8 Scope

- Voice responses use a voice-specific `AssistantCore` path.
- `VOICE_RESPONSE_MODE=concise` is the default for voice commands only; normal text chat keeps the normal `SYSTEM_PROMPT`.
- `VOICE_CONCISE_INSTRUCTION` controls the extra instruction appended to voice-mode OpenAI prompts.
- `VOICE_FOLLOW_UP_TIMEOUT_SECONDS` controls the follow-up listening window.
- Spoken standby can be disabled with `VOICE_LOOP_SPEAK_STANDBY=false` or changed with `VOICE_LOOP_STANDBY_MESSAGE`.
- Assistant response speech no longer adds an extra cooldown before follow-up listening starts.
- Voice loop TTS calls are centralized as a low-risk foundation for later interruption work.

## v0.2.0 Phase 9 Scope

- Follow-up listening is more forgiving with `VOICE_FOLLOW_UP_TIMEOUT_SECONDS=15` by default.
- `Standing by.` remains the visual return-to-sleep state, but it is not spoken by default because it can delay natural follow-up speech.
- `VOICE_COMMAND_INCOMPLETE_PHRASES` rejects broken partial transcripts such as `what's the`, `what is the`, `tell me about`, `can you`, `could you`, and `please`.
- Incomplete transcripts are rejected locally before `AssistantCore` or OpenAI and get one retry capture.
- Live voice-loop logging includes average RMS, max RMS, VAD crossed status, raw transcript, cleaned transcript, accepted status, and rejection reason.
- `logs/voice_loop.log` uses a managed append-only Loguru sink to avoid Windows rotation/retention races.
- The GUI voice surface now shows a larger assistant state area, orb feedback, transcript panel, response panel, live provider/wake/RMS/VAD diagnostics, and clearer voice-loop controls.

## v0.2.0 Phase 10 Scope

- Speech repair runs after STT cleanup and before command validation.
- Jarvis preserves the raw transcript, then produces a repaired transcript, confidence, strategy, and repair reason.
- Repaired command text is what reaches validation and `AssistantCore` when repair succeeds; broken raw speech is not sent to OpenAI.
- Repair uses configured rules, incomplete phrase rules, recent accepted voice-command context, common intents, and optional OpenAI repair.
- `VOICE_USE_OPENAI_REPAIR=false` by default. When enabled, OpenAI repair is skipped for empty speech, punctuation-only speech, filler speech, and clearly invalid very short input.
- Low-confidence repairs ask for confirmation with `Did you mean: <repaired command>?` before continuing.
- GUI diagnostics show `Speech`, `Interpreted`, repair confidence, and repair strategy.

## Voice Speed Polish

- The live voice loop now uses shorter default capture windows and starts command capture immediately after wake detection.
- Wake acknowledgement speech is off by default, so `Yes sir?` no longer adds delay unless explicitly enabled.
- Live assistant responses can be displayed instantly in the GUI with `VOICE_LOOP_SPEAK_RESPONSES=false`.
- The voice loop logs wake, command, OpenAI, TTS, and total-turn timings for turn-by-turn latency checks.
- The GUI shows a larger assistant dashboard with a voice-stack card, a timing card, and a more prominent start/stop control block.

## Phase 10 Scope

- In-memory short-term conversation history for the current session only.
- Conversation history keeps the last `CONVERSATION_HISTORY_MAX_MESSAGES` messages.
- Chat and voice loop requests send recent history to OpenAI when history is enabled.
- CLI command: `py main.py --chat-session`.
- Session exit commands: `exit`, `quit`, and `bye`.
- `reset conversation` clears only the current short-term history.
- Conversation history is not written to disk.

## Phase 12.1 Long-Term Memory

- SQLite-only persistent long-term memory.
- Structured entries store an id, key, category, value, source, creation time,
  and update time.
- Supported commands include `my name is ...`, `remember that ...`,
  `remember my ...`, `forget that ...`, `forget my ...`,
  `what do you remember about ...`, `what is my name`,
  `what do you remember`, and `reset memory`.
- Memory settings: `MEMORY_ENABLED=true`, `MEMORY_DB_PATH=memory.db`.
- `MEMORY_CONFIRM_NAMES=true` asks for confirmation before storing short or
  unusual names. Reply `yes` to save or `no` to discard the pending name.
- Only explicit personal facts and preferences are stored.
- Sensitive secrets such as API keys, passwords, and payment card details are rejected.
- Memory persists across restarts because it is stored in SQLite.
- Relevant memories are added to OpenAI context as user-provided factual data,
  not instructions. The current user message overrides conflicting memory.

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
VOICE_VAD_WINDOW_MS=80
VOICE_VAD_NOISE_MULTIPLIER=3.0
VOICE_VAD_SILENCE_MS=650
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
py main.py --wake-debug
```

The command records one short microphone clip, transcribes it with Faster Whisper, and checks whether the transcript matches the configured wake phrase or aliases. Wake detection now prefers OpenWakeWord when available and falls back to manual command mode if it is not installed or the model is missing.

Wake settings:

```dotenv
WAKE_PHRASE=hey jarvis
WAKE_ALIASES=jarvis,hey jarvis,hi jarvis,okay jarvis,wake up jarvis,yo jarvis,jarvis please,service,jervis,travis,charities,office,jar of this,out of this,turn this
WAKE_THRESHOLD=0.72
WAKE_MATCH_THRESHOLD=0.72
WAKE_LISTEN_SECONDS=2.0
WAKE_PROVIDER=openwakeword
WAKE_FALLBACK_PROVIDER=whisper_fuzzy
OPENWAKEWORD_ENABLED=true
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

Repeat the single-word wake test with:

```powershell
py main.py --wake-jarvis-test --repeat 3
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
11. Repairs the cleaned transcript when speech repair is enabled.
12. Validates the repaired command and rejects bad short transcripts locally.
13. Sends accepted repaired command text to the existing `AssistantCore` stub.
14. Prints the raw command transcript, repaired command, repair confidence/strategy, accepted status, rejection reason when rejected, and placeholder Jarvis response when accepted.

Voice command capture settings:

```dotenv
WAKE_LISTEN_SECONDS=5
VOICE_COMMAND_START_DELAY_SECONDS=1.0
VOICE_COMMAND_RECORD_SECONDS=7
VOICE_COMMAND_MIN_WORDS=2
VOICE_COMMAND_REJECT_PHRASES=you,uh,um,hmm,yeah,okay
VOICE_COMMAND_INCOMPLETE_PHRASES=what's the,what is the,tell me about,can you,could you,weather in,remind me,please
VOICE_SPEECH_REPAIR_ENABLED=true
VOICE_USE_OPENAI_REPAIR=false
VOICE_REPAIR_RULES=did it noting him today whats the=>what's the weather in {weather_default_city} today;did it nottingham today whats the=>what's the weather in {weather_default_city} today
VOICE_REPAIR_INCOMPLETE_PHRASES=what's the,what is the,tell me about,can you,could you,weather in,remind me,please
VOICE_REPAIR_CONFIRMATION_THRESHOLD=0.75
VOICE_REPAIR_CONFIRMATION_SECONDS=3
VOICE_COMMAND_RETRY_ON_REJECT=true
VOICE_COMMAND_MAX_RETRIES=1
```

If the command transcription is empty, punctuation-only, too short, one of the configured rejected phrases, or an incomplete partial phrase, Jarvis prints:

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

This records one command sample without requiring wake detection. It prints the provider, sample rate, record seconds, average RMS, max RMS, noise floor, configured and effective VAD thresholds, VAD trigger point, raw transcript, transcript confidence when available, clean transcript, repaired command, wake score, command score, repair confidence, repair strategy, accepted status, rejection reason when rejected, and the diagnostic log path.

Use this when wake detection works but command capture produces bad transcripts such as `You`, `uh`, or punctuation-only text.

Detailed command capture logs are saved to:

```text
logs/command_capture.log
```

## Experimental Phase 10 - Lightweight Fast Voice Mode

Fast voice mode is a separate low-latency path inspired by the tutorial's simple terminal interaction. It does not replace the full wake loop, OpenWakeWord, AssistantCore, OpenAI routing, or the red HUD GUI.

```powershell
python main.py --fast-voice
```

The default `enter` activation waits for Enter, records immediately, stops after the configured trailing silence once speech has started, transcribes once, repairs and validates the command, routes it through `AssistantCore`, and prints the response before optional TTS. A hard capture limit prevents a missed VAD event from creating a long wait. Type `q` at the activation prompt to exit.

Faster Whisper is created once per fast-mode runner and reused for every turn. With warm-up enabled, the configured model is loaded once when the interactive session starts, before the first command timer. The startup line reports this one-time cost; per-command `stt_warmup_ms` remains zero. `WHISPER_MODEL=base.en` is the default; `small.en` is available when higher accuracy is worth the additional latency.

Interactive `--fast-voice` also opens one persistent microphone stream and reuses it across commands. The stream is started and stopped around each capture so audio spoken while waiting at the Enter prompt is not treated as a command. `--fast-command-test` intentionally retains a one-shot stream as a diagnostic fallback.

Wake-only phrases such as `Wake up, Jarvis`, `Hey Jarvis`, and `Jarvis` are handled locally with `I'm listening.` They are not rejected and are not sent to OpenAI as empty commands.

Supported activation modes:

- `enter`: push-to-talk style; press Enter for each command.
- `direct`: capture one command immediately and exit.
- `clap`: wait locally for a short high-energy clap, then capture commands. Clap detection is experimental and never sends audio anywhere by itself.

```dotenv
FAST_VOICE_ENABLED=true
FAST_VOICE_ACTIVATION=enter
FAST_VOICE_RECORD_SECONDS=4.0
FAST_VOICE_MAX_SECONDS=1.8
FAST_VOICE_MIN_SPEECH_MS=300
FAST_VOICE_SILENCE_MS=300
FAST_VOICE_FAST_STOP_ENABLED=true
FAST_VOICE_SHORT_COMMAND_SILENCE_MS=250
FAST_VOICE_LONG_COMMAND_SILENCE_MS=450
FAST_VOICE_PREROLL_MS=250
FAST_VOICE_TTS_ENABLED=false
FAST_VOICE_TTS_MODE=off
FAST_VOICE_WAKE_ONLY_RESPONSE=I'm listening.
FAST_VOICE_EMPTY_AUDIO_RESPONSE=I heard sound but could not understand it.
FAST_VOICE_WARM_STT_ON_START=true
FAST_VOICE_CONCISE_RESPONSES=true
FAST_VOICE_CONCISE_INSTRUCTION=Respond in one short sentence. Be direct unless the user asks for detail.
VOICE_INPUT_DEVICE=Microphone Array
WHISPER_MODEL=base.en
```

Run a single full-path fast command test with:

```powershell
python main.py --fast-command-test
```

Terminal fast voice uses the lower of the backwards-compatible `FAST_VOICE_RECORD_SECONDS` setting and `FAST_VOICE_MAX_SECONDS`. GUI fast voice treats `GUI_FAST_VOICE_MAX_SECONDS` as a soft limit and `GUI_FAST_VOICE_HARD_MAX_SECONDS` as an absolute cap. After speech starts, `GUI_FAST_VOICE_NOISE_GATE_MULTIPLIER` applies a stronger adaptive continuation gate and `GUI_FAST_VOICE_END_SILENCE_MS` controls how quickly capture ends. With fast-stop enabled, speech up to one second uses the short-command silence window; longer speech uses the long-command window. The minimum speech duration and pre-roll protect short commands and their first word. Disable fast-stop to use the fixed `FAST_VOICE_SILENCE_MS` value. If VAD hears sound but STT produces no transcript, Jarvis responds locally instead of sending an empty command.

Fast voice uses its own concise system instruction by default to reduce generated response length while leaving text chat and the full voice loop unchanged. Set `FAST_VOICE_CONCISE_RESPONSES=false` for normal-length answers.

Each result logs `capture_ms`, `audio_record_ms`, `audio_prepare_ms`, `stt_warmup_ms`, `vad_wait_ms`, `speech_ms`, `trailing_silence_ms`, `transcribe_ms`, `openai_ms`, `tts_ms`, and `total_ms`. `capture_ms` and `audio_record_ms` measure only blocking microphone reads; per-command stream start/stop, conversion, and VAD processing are reported separately as `audio_prepare_ms`. Persistent device discovery and stream construction appear once as `audio_session_prepare_ms` on the startup line. Here `openai_ms` measures the existing `AssistantCore` response stage, which may complete locally without an OpenAI request. Detailed logs are written to `logs/fast_voice.log`.

## Voice Loop

```powershell
py main.py --voice-loop
```

The voice loop keeps Jarvis running until stopped:

1. Sleeps while waiting for the wake phrase.
2. Uses the selected wake provider.
3. When OpenWakeWord is active, listens in short chunks before any wake transcription.
4. Falls back to Whisper fuzzy wake detection when OpenWakeWord is unavailable.
5. Starts command capture immediately after wake detection; the wake acknowledgement speech is off by default.
6. Records one command clip using the shorter default command window.
7. Repairs the cleaned transcript using rules, context, common intents, and optional OpenAI repair.
8. Validates the repaired command text.
9. Asks for confirmation before using a low-confidence repair.
10. Stops cleanly if the command is `stop listening`, `go to sleep`, `sleep jarvis`, `jarvis sleep`, `exit jarvis`, `shutdown jarvis`, `that is all`, or `thank you jarvis`.
11. Rejects bad short transcripts locally with `I didn’t catch that, please repeat.` and retries command capture once by default.
12. Sends accepted repaired commands to `AssistantCore`.
13. Speaks accepted responses only when `VOICE_LOOP_SPEAK_RESPONSES=true`.
14. Enters one configurable `Listening for follow-up...` window after a successful response.
15. Sends valid follow-up commands to `AssistantCore` without requiring the wake phrase again.
16. Rejects invalid or incomplete non-empty follow-ups locally, retries follow-up capture once, and returns to sleep if the retry is invalid or no follow-up is heard.
17. Speaks the configured standby message only after follow-up mode is finished and Jarvis is returning to sleep, when standby speech is enabled.
18. Prints a summary on exit with wake attempts, successful wakes, commands handled, empty commands, errors, and the latest turn timing summary.

For GUI visibility, the loop emits explicit events for rejected commands, retrying command capture, follow-up listening, accepted commands and follow-ups, assistant responses, return-to-sleep state, wake diagnostics, command capture RMS/VAD diagnostics, and speech repair diagnostics.

Press Ctrl+C to stop the CLI loop. Detailed voice loop logs are saved to:

```text
logs/voice_loop.log
```

Voice loop polish settings:

```dotenv
VOICE_COMMAND_START_DELAY_SECONDS=0
VOICE_COMMAND_RECORD_SECONDS=5
VOICE_VAD_WINDOW_MS=80
VOICE_VAD_NOISE_MULTIPLIER=3.0
VOICE_VAD_SILENCE_MS=650
VOICE_LOOP_SPEAK_WAKE_ACK=false
VOICE_LOOP_SPEAK_RESPONSES=true
VOICE_FOLLOW_UP_TIMEOUT_SECONDS=10
VOICE_RESPONSE_MODE=concise
VOICE_CONCISE_INSTRUCTION=Answer voice commands in one or two short sentences unless the user asks for detail.
VOICE_LOOP_SPEAK_STANDBY=false
VOICE_LOOP_STANDBY_MESSAGE=Standing by.
```

Set `VOICE_RESPONSE_MODE=normal` to use the standard chat prompt for voice responses. Set `VOICE_LOOP_SPEAK_WAKE_ACK=false` to keep the wake acknowledgement visual only. Set `VOICE_LOOP_SPEAK_RESPONSES=false` to display responses instantly in the GUI without waiting for speech. Set `VOICE_LOOP_SPEAK_STANDBY=false` to keep the visual `Standing by.` state without speaking it.

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

The memory test uses an isolated SQLite database and exercises structured name
and preference storage, targeted recall, listing, forgetting, and reset without
touching the main memory database.

Manual memory examples:

```powershell
py main.py --chat-session
```

```text
You: My name is Zaid.
Jarvis: I heard your name as Zaid. Should I remember that?
You: Yes.
You: What is my name?
You: Remember that I prefer dark red UI.
You: What do you remember about UI?
You: Correct my name to Zaid.
You: Forget my name.
```

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

## Phase 13.1 Desktop App Control

- Safe Windows desktop application launcher for whitelisted commands only.
- CLI commands: `py main.py --app-launcher-check`, `py main.py --resolve-app notepad`, and `py main.py --launch-app notepad`.
- Assistant commands: `open chrome`, `open edge`, `open notepad`,
  `open calculator`, `open file explorer`, `open vs code`, and
  `open spotify`.
- Natural aliases such as `visual studio code`, `windows explorer`,
  `google chrome`, and `microsoft edge` map only to their whitelisted app.
- Chrome, Edge, VS Code, and Spotify are resolved from PATH and common Windows
  installation locations. Spotify is launched only when installed.
- Launcher settings: `APP_LAUNCHER_ENABLED=true`,
  `APP_LAUNCHER_ALLOWED_APPS=notepad=notepad.exe,calculator=calc.exe,file explorer=explorer.exe,chrome=,edge=,vscode=,spotify=,docker=`.
- Launcher logs are saved to `logs/app_launcher.log`.
- App-launch commands are handled locally and are never sent to OpenAI.

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

Jarvis can launch only apps listed in `APP_LAUNCHER_ALLOWED_APPS`. If an app
is missing, not installed, or cannot be resolved, Jarvis reports that locally
and does not send the command to OpenAI.

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
- Safe browser search for fixed providers only.
- CLI commands: `py main.py --website-check` and `py main.py --open-site google`.
- Assistant commands: `open google`, `open youtube`, `open github`, `open chatgpt`, `open gmail`, `open calendar`, `open outlook`, `search google for jarvis`, and `search youtube for jarvis`.
- Website settings: `WEBSITE_LAUNCHER_ENABLED=true`, `WEBSITE_ALLOWED_SITES=google=https://www.google.com,youtube=https://www.youtube.com,github=https://github.com,chatgpt=https://chatgpt.com,gmail=https://mail.google.com,calendar=https://calendar.google.com,blackboard=,outlook=https://outlook.office.com`.
- Raw URLs are rejected and sites without configured URLs fail safely.
- Search queries are URL-encoded before launch.
- Website logs are saved to `logs/website_launcher.log`.

## Phase 13.3 Scope

- Safe folder opening for whitelisted folders only.
- Assistant commands: `open downloads`, `open documents`, `open desktop`, `open pictures`, `open videos`, `open music`, `open my jarvis folder`, `open jarvis project`, `open jarvis in vs code`, and `show recent downloads`.
- Folder paths are restricted to the configured whitelist plus the Jarvis project root.
- `open jarvis in vs code` reuses the safe VS Code launcher resolution path.
- Recent downloads are read from the whitelisted Downloads folder and shown locally.
- Folder logs are saved to `logs/folder_control.log`.
- Folder access settings: `FILE_ACCESS_ENABLED=true`, `FILE_ACCESS_ALLOWED_FOLDERS=documents=%USERPROFILE%\Documents,desktop=%USERPROFILE%\Desktop,downloads=%USERPROFILE%\Downloads,pictures=%USERPROFILE%\Pictures,videos=%USERPROFILE%\Videos,music=%USERPROFILE%\Music`.

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

- Vision foundation for manual screenshot capture, OCR diagnostics, and screen capture storage.
- Enable with `SCREEN_VISION_ENABLED=true`, `SCREENSHOT_ENABLED=true`, and `OCR_ENABLED=true`.
- Screenshot files are saved under `SCREENSHOT_DIR=data/screenshots` by default.
- OCR provider: `OCR_PROVIDER=tesseract`.
- OCR output is capped by `OCR_MAX_OUTPUT_CHARS=4000`.
- Run `py main.py --vision-check` to inspect screenshot/OCR readiness.
- Run `py main.py --screenshot-test` to capture a screenshot after confirmation.
- Run `py main.py --ocr-test "<image_path>"` to OCR a local image after confirmation.
- Assistant commands: `take screenshot`, `read screen text`, `read my screen`, and `read my screen text`.
- Screenshot capture and OCR are high risk and require permission plus confirmation.
- Jarvis does not click or type on the screen.
- Vision logs are saved to `logs/vision.log`.

## Phase 31 Scope

- OpenAI vision analysis for screenshots and local images only after confirmation.
- Enable with `OPENAI_VISION_ENABLED=true`.
- OpenAI vision model: `OPENAI_VISION_MODEL=gpt-4o-mini`.
- Maximum image size: `OPENAI_VISION_MAX_IMAGE_BYTES=5000000`.
- Run `py main.py --vision-analyze "<image_path>"` to analyze a whitelisted screenshot or test image after confirmation.
- Assistant commands: `analyze screenshot`, `what is on my screen`, `look at my screen`, `describe my screen`, and `describe screen`.
- If OpenAI vision is not configured, the command still captures a screenshot and returns the saved path.
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
