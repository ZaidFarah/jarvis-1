# Jarvis Architecture

## Purpose

 Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 added a limited local voice foundation for microphone diagnostics and provider interfaces. Phase 2.0 added OpenWakeWord support with Whisper fuzzy fallback. Phase 2.1 added OpenWakeWord installation and a controlled diagnostic path before making it the default live wake route. Phase 2.5 improved diagnostic reliability and reporting. Phase 3 added one-shot Faster Whisper transcription testing. Phase 4 added controlled wake phrase detection as a test mode only. Phase 5 added a controlled one-shot voice command test mode, keeps OpenWakeWord optional/diagnostic for now, restores Whisper fuzzy as the safe default live wake provider, and rejects bad short command transcripts before OpenAI. The v0.2.0 Phase 6 hardening pass makes the live voice loop report rejected commands, retry state, accepted commands, assistant responses, and return-to-sleep state clearly to the GUI while preserving local rejection before `AssistantCore` or OpenAI. The v0.2.0 Phase 7 pass adds one short follow-up listening window after successful assistant responses, so a valid follow-up command can continue through `AssistantCore` and OpenAI without requiring the wake phrase again. The v0.2.0 Phase 8 polish pass makes the follow-up timeout configurable, adds a voice-specific concise response path, makes standby speech suppressible/configurable, removes the extra response-to-follow-up cooldown, and centralizes voice-loop TTS calls for future interruption work. The v0.2.0 Phase 9 usability pass improves live capture timing, incomplete transcript rejection, Windows-safe voice-loop logging, and the assistant-style GUI voice surface. The v0.2.0 Phase 10 speech intelligence pass adds transcript repair, confirmation for low-confidence repairs, and raw-versus-interpreted speech diagnostics before command validation. The v0.2.0 voice speed polish pass shortens command and follow-up capture defaults, makes wake acknowledgement speech optional and off by default, makes live response speech optional, and adds turn timing diagnostics and a denser assistant dashboard. Phase 6 added OpenAI connection diagnostics. Phase 7 connects `AssistantCore` to OpenAI chat with local fallback. Phase 8 adds safe local text-to-speech for Jarvis responses. Phase 8.5 adds OpenAI TTS as the preferred voice provider with local `pyttsx3` fallback. Phase 8.6 improves one-shot command capture timing after wake detection. Phase 9 adds the first continuous voice loop. Phase 9.5 polishes that loop with spoken status feedback, cooldowns, summary counters, and richer GUI state. Phase 10 adds short-term in-memory conversation history for the current session. Phase 11 adds SQLite-backed persistent local memory for explicit user-approved facts only. Phase 12 adds safe weather lookups through OpenWeatherMap with explicit configuration and fallback handling. Phase 13 adds local SQLite reminders with simple explicit command routing. Phase 14 adds manual due-reminder checking and optional spoken reminder output. Phase 15 adds a local reminder watcher that runs only while Jarvis is active. Phase 16 adds optional Windows toast notifications. Phase 17 adds a safe local application launcher. Phase 18 adds a safe website launcher for whitelisted sites only. Phase 19 adds safe read-only file access for whitelisted folders only. Phase 20 adds a central permission broker that classifies sensitive actions before future confirmation flows exist. Phase 21 adds interactive confirmation for medium and high-risk actions. Phase 22 adds safe read-only file content reading for whitelisted folders with confirmation gating. Phase 23 adds safe file summarization for whitelisted text files with a second confirmation before OpenAI upload. Phase 24 adds a safe Google Calendar read-only foundation with confirmation-gated reads. Phase 25 adds Google Calendar OAuth setup and read-only event queries. Phase 36 adds packaging scaffolding with runtime path resolution and a safe runtime check without building the final executable. Phase 37 adds the first Windows PyInstaller build and packaged EXE diagnostics without changing runtime behavior. Phase 38 adds external first-run packaged config initialization under `%APPDATA%` without bundling secrets. Phase 39 adds packaged smoke test scripts and launcher scripts. Phase 40 adds optional current-user Windows startup registration through the Run registry key after confirmation.

## Phase 1 Components

### Application Bootstrap

`main.py` starts `JarvisApplication` from `app/application.py`. The application object loads settings, configures logging, creates the Qt application, wires the assistant core into the GUI, and handles shutdown.

### Configuration

`config/settings.py` uses Pydantic Settings with the `JARVIS_` environment prefix. Settings may be loaded from `.env`, but Phase 1 does not define or require secrets.

### Logging

`services/logging_service.py` configures Loguru for console logs and `logs/jarvis.log`. It also provides a managed append-only file sink helper for live diagnostics so Windows does not rotate active voice log files while microphone capture is running. Diagnostic logs are written separately for audio, STT, wake, voice command, OpenAI checks, TTS, command capture, and the live voice loop. Detailed provider, tool, and security audit logging will be added in later approved phases.

### Startup Service

`services/startup_service.py` manages optional Windows startup registration. It uses only the current-user Run registry key at `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, so it does not require admin permissions and never writes system-wide startup keys. Startup enable and disable are medium-risk actions routed through the permission broker and confirmation layer before any registry write. Source mode targets `run_jarvis.bat` when present, while packaged mode targets the known `Jarvis.exe` path.

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

`assistant/core.py` accepts text commands and routes them to OpenAI when enabled and configured. Normal text chat uses `SYSTEM_PROMPT`. Voice loop calls use `handle_voice_command`, which can append `VOICE_CONCISE_INSTRUCTION` when `VOICE_RESPONSE_MODE=concise`. If OpenAI is disabled, missing a key, or errors, it returns the local placeholder fallback. It does not run tools, access files, or store memory.

### Voice Foundation

`voice/` contains the Phase 2 and 2.5 audio layer:

- `audio_diagnostics.py`: lists microphone devices, runs a short local stream test, writes `logs/audio_diagnostics.log`, and formats readable diagnostic reports.
- `interfaces.py`: defines VAD, speech-to-text, and text-to-speech provider contracts.
- `vad.py`: provides a small RMS-based VAD implementation for diagnostics only.
- `stt.py`: contains the interface-only provider, Faster Whisper provider, and STT provider factory.
- `transcription_diagnostics.py`: records one microphone clip, transcribes it through Faster Whisper, and writes `logs/stt_diagnostics.log`.
- `tts.py`: contains the OpenAI TTS provider, safe local `pyttsx3` fallback, provider factory, generated audio playback, TTS result formatting, `logs/audio/` output, and `logs/tts.log` sink.
- `wake.py`: detects the configured wake phrase, aliases, and close fuzzy matches using `difflib.SequenceMatcher`.
- `wake_provider.py`: resolves the selected wake provider, detects OpenWakeWord availability, and keeps Whisper fuzzy wake detection as the current default fallback.
- `wake_diagnostics.py`: records one microphone clip, transcribes it, runs wake detection, and writes `logs/wake_diagnostics.log`.
- `openwakeword.py`: checks the installed OpenWakeWord package, verifies model availability, captures short microphone samples, provides tuning calibration, reports microphone RMS and VAD results, and writes `logs/openwakeword.log`. OpenWakeWord remains diagnostic/optional until a better user-matched model is available.
- `command_validation.py`: rejects empty, punctuation-only, configured filler phrases such as `you`, `uh`, `um`, `hmm`, `yeah`, and `okay`, configured incomplete transcripts such as `what's the`, `tell me about`, `can you`, `weather in`, `remind me`, and `please`, and commands below the configured minimum word count.
- `speech_repair.py`: runs after STT cleanup and before validation, preserving raw speech while producing repaired transcript, confidence, strategy, and reason. It uses configured rules, recent accepted voice-command context, common intents, and optional OpenAI repair when enabled.
- `command_capture.py`: records one command sample without requiring wake detection, reports microphone RMS/VAD, raw transcript, repaired command, speech repair confidence/strategy, accepted status, rejection reason, exposes shared audio metric helpers for the live loop, and writes `logs/command_capture.log`.
- `voice_command_test.py`: records one wake phrase clip, waits briefly after wake detection, optionally plays a Windows beep, records one command clip using the command duration setting, repairs and validates command text, sends only accepted repaired command text to `AssistantCore`, optionally speaks the response, and writes `logs/voice_command_test.log`.
- `voice_loop.py`: runs the continuous voice loop, uses the selected wake provider, falls back to Whisper fuzzy wake detection when needed, starts command capture immediately after wake detection, optionally speaks a wake acknowledgment, repairs cleaned STT transcripts before validation, asks for confirmation on low-confidence repairs, rejects bad and incomplete command transcripts locally with retry before `AssistantCore` or OpenAI, handles accepted repaired commands through the voice-specific `AssistantCore` path, optionally skips live response speech for faster follow-up, enters a configurable follow-up listening window before sleeping, accepts a valid follow-up command without another wake phrase, emits rejected/retry/follow-up/accepted/response/sleep events plus wake score, RMS/VAD, speech repair diagnostics, and turn timing diagnostics for the GUI and CLI, handles stop commands, centralizes TTS calls for future interruption work, applies cooldown only where needed for spoken status messages rather than between response speech and follow-up capture, reports summary counters, and writes `logs/voice_loop.log` through the managed append-only sink.
- `conversation.py`: keeps short-term in-memory conversation turns, trims to the configured maximum, and formats recent history for prompts.
- `memory/store.py`: manages SQLite persistence for explicit user-approved memories, rejects sensitive secrets, and supports remember/list/forget/reset operations.
- `integrations/weather_service.py`: performs explicit weather checks, fetches current weather only when enabled and keyed, redacts secret-like error text, and writes `logs/weather.log`.
- `reminders/service.py`: manages explicit reminder commands, parses simple time strings, routes to SQLite storage, and writes `logs/reminders.log`.
- `reminders/store.py`: persists reminders with title, remind_at, status, created_at, and updated_at fields.
- `reminders/scheduler.py`: runs the local reminder watcher loop, checks due reminders at the configured interval, and can speak due reminders while Jarvis is running.

No ElevenLabs, voice cloning, real-time OpenAI voice conversation, permissions system, startup background service, or tool execution is implemented in Phase 9.

### GUI

`gui/main_window.py` contains the PySide6 floating Jarvis shell:

- dark frameless assistant-style window
- animated orb and large current-state panel
- system tray icon
- manual command input
- microphone test button
- start and stop voice loop controls
- current loop status, last command, and last response fields
- live loop event handling for rejected command, retrying capture, follow-up listening, accepted command and follow-up, assistant response, sleeping state, wake score, provider, RMS, VAD diagnostics, raw speech, interpreted speech, repair confidence, repair strategy, and turn timings
- separate transcript and response panels
- status states: Sleeping, Listening, Thinking, Speaking, Follow-up, Error
- diagnostics controls for startup check, startup enable, and startup disable

The window can be hidden to the tray and safely exited from the tray menu.

## Future Architecture

Future phases should add capabilities behind explicit approval gates:

- Phase 2: microphone diagnostics and voice provider interfaces
- Phase 2.5: clearer diagnostics, dedicated audio log, stronger microphone suggestions
- Phase 3: one-shot Faster Whisper speech-to-text diagnostic
- Phase 4: one-shot wake phrase detection diagnostic
- Phase 5: controlled one-shot voice command test with command validation and command-capture diagnostics
- Phase 6: OpenAI connection diagnostics only
- Phase 7: OpenAI-backed AssistantCore responses with fallback
- Phase 8: safe local pyttsx3 text-to-speech output
- Phase 8.5: OpenAI text-to-speech output with pyttsx3 fallback
- Phase 8.6: clearer one-shot command capture timing after wake detection
- Phase 9: first continuous one-command-at-a-time voice loop
- Phase 12: safe OpenWeatherMap weather lookups
- Phase 13: local SQLite reminders
- Phase 14: manual reminder checking
- Phase 15: local reminder watcher
- Phase 3: OpenAI provider, agent routing, typed tool interfaces
- Phase 4: local memory and summaries
- Phase 5: permission-gated file, browser, and desktop tools
- Phase 6: weather, Gmail, Google Calendar, reminders
- Phase 7: screenshot, OCR, and vision
- Phase 8: packaging, Windows startup, diagnostics
- Phase 17: safe local application launcher

## Safety Boundary

The v0.2.0 voice hardening phases add no tools, no startup background service, and no permissions system. They cannot access email, calendar, browser automation, desktop automation, memory, screenshots, or local file content. OpenAI usage is limited to accepted plain text chat responses and text-to-speech from the user command text, accepted follow-up text, or assistant response. Empty, punctuation-only, configured filler, and configured incomplete command transcripts are rejected locally before OpenAI; the follow-up path uses the same validation boundary before routing text to `AssistantCore`. The v0.2.0 Phase 10 speech repair stage runs before that validation boundary, but only the accepted repaired command is routed to `AssistantCore`; broken raw transcripts are kept for diagnostics. Optional OpenAI repair is disabled by default and is skipped for empty, filler, punctuation-only, and clearly invalid very short transcripts. The voice speed polish settings only adjust latency and presentation, not assistant capabilities. Voice concise mode changes only the OpenAI prompt used for accepted voice commands; normal text chat keeps the normal prompt. The OpenAI TTS voice direction is an original assistant voice: calm, mature, professional, British-inspired, deep but clear, slightly cinematic, and natural paced. It must not clone or imitate a real actor or copyrighted movie character.

Phase 10 adds only in-memory conversation context. It does not persist history to disk or add long-term memory, databases, or retrieval systems.

Phase 11 adds only SQLite-backed memory for explicit user-approved facts. It does not add embeddings, vector databases, long-term semantic search, or automatic conversation logging into memory.

Phase 12 adds only explicit weather lookups through OpenWeatherMap. It does not add automatic location tracking, Gmail, Calendar, browser automation, desktop automation, file tools, vision, or a broader tools system.

Phase 13 adds only local reminders backed by SQLite. It does not add background notifications, scheduled delivery, Gmail, Calendar, browser automation, desktop automation, file tools, vision, or a broader scheduler.

Phase 14 adds only manual reminder checking. It does not add always-running scheduling, toast notifications, background daemons, or any broader notification system.

Phase 15 adds only a local reminder watcher that runs while Jarvis is active. It does not add a Windows service, startup persistence, toast notifications, or a background daemon outside the app/CLI lifecycle.

Phase 16 adds only optional Windows toast notifications. It does not add a startup service, background daemon, Gmail, Calendar, browser automation, desktop automation, file tools, vision, or LangGraph.

Phase 17 adds only a whitelisted local application launcher. It does not execute arbitrary shell commands, expose raw paths, add desktop automation, browser automation beyond whitelisted app launches, Gmail, Calendar, file tools, vision, startup services, or LangGraph. Phase 17.5 improves resolution and launch reliability by preferring `subprocess.Popen` for simple executables and only using `os.startfile` for whitelisted resolved paths.

Phase 18 adds only a whitelisted website launcher. It does not browse content, click pages, fill forms, automate browsers, read website text, accept raw user URLs, add Playwright, add Selenium, or add a broader web automation layer.

Phase 19 adds only read-only access to whitelisted folders. It does not read file contents, write files, delete files, rename files, move files, accept arbitrary paths, traverse outside the allowlist, send file content to OpenAI, or add a broader file tool system.

Phase 20 adds only permission classification and logging. It does not add interactive confirmations yet, block the existing low-risk actions, or expand the assistant into a broader policy engine beyond the approved action map.

Phase 21 adds only interactive confirmation for classified medium/high-risk actions. It does not add new risky capabilities, does not make blocked actions confirmable, and does not change the behavior of the existing low-risk paths.

Phase 22 adds only read-only file content reads for whitelisted folders. It does not add file writing, deleting, moving, renaming, arbitrary path access, binary inspection tools, OpenAI uploads, or file summarization. Reads are limited by extension, byte count, output length, permission classification, and confirmation.

Phase 23 adds only file summarization for whitelisted text files. It does not add file writing, deleting, moving, renaming, arbitrary path access, binary inspection tools, auto-memory, or any OpenAI upload without explicit confirmation. The file content read and the OpenAI summary request are each gated separately.

Phase 24 adds only read-only Google Calendar lookups. It does not add event creation, editing, deletion, Gmail, browser automation, desktop automation, or broader Google API access beyond the read-only calendar query path. Calendar reads remain high risk and confirmation-gated.

Phase 25 adds only OAuth setup and read-only event queries for Google Calendar. It does not add event creation, editing, deletion, Gmail, browser automation, desktop automation, or broader Google API access beyond the readonly calendar scope. The token is stored locally and the client secret is never logged or printed.

Phase 26 adds only Google Calendar event creation. It keeps creation separate behind `CALENDAR_CREATE_ENABLED` and `CALENDAR_WRITE_SCOPES`, requires permission broker classification and explicit confirmation, and refuses to create events when the token only has read-only scope. It does not add event editing, deletion, Gmail, browser automation, desktop automation, or any broader Google API access.

Phase 27 adds only Gmail unread metadata access. It keeps Gmail read-only behind `GMAIL_ENABLED` and `GMAIL_SCOPES`, requires permission broker classification and explicit confirmation before reading unread messages, and limits output to sender, subject, snippet, and date when available. It does not add sending, drafting, deleting, archiving, full-body reads, browser automation, desktop automation, or broader Gmail API access.

Phase 28 adds only Gmail draft creation. It keeps draft creation behind `GMAIL_DRAFT_ENABLED` and `GMAIL_DRAFT_SCOPES`, requires permission broker classification and explicit confirmation before creating a draft, and does not add sending, deleting, archiving, full-body reads, browser automation, desktop automation, or broader Gmail API access. If the token only has Gmail readonly scope, Jarvis refuses to create a draft until the user reruns Gmail auth after enabling draft mode.

Phase 29 adds only Gmail draft listing and sending an existing draft by ID. It keeps those paths behind `GMAIL_SEND_DRAFT_ENABLED` and `GMAIL_SEND_SCOPES`, requires permission broker classification and explicit confirmation before listing or sending drafts, and does not add free-form direct email sending, deleting, archiving, full-body reads, browser automation, desktop automation, or broader Gmail API access. If the token only has Gmail readonly scope, Jarvis refuses to list or send drafts until the user reruns Gmail auth after enabling send-draft mode.

Phase 30 adds only vision diagnostics for screenshot capture and OCR. It keeps those paths behind `VISION_ENABLED`, `SCREENSHOT_ENABLED`, and `OCR_ENABLED`, requires permission broker classification and explicit confirmation before capturing screenshots or reading screen text, saves screenshots only under the configured screenshot directory, and does not add OpenAI vision, screen control, clicks, typing, browser automation, desktop automation, or broader image analysis.

Phase 31 adds OpenAI vision analysis for approved screenshots and local test images. It keeps image upload behind `OPENAI_VISION_ENABLED`, caps image size with `OPENAI_VISION_MAX_IMAGE_BYTES`, requires separate confirmation for screenshot capture and image upload, rejects obvious password/banking/secret screens before upload, and still does not add screen control, clicks, typing, or desktop/browser automation.

Phase 33 adds an experimental LangGraph-style agent layer beside `AssistantCore`. It only classifies requests and dispatches into the existing weather, reminders, app launcher, website launcher, file access, calendar, Gmail, vision, or fallback chat paths. It does not replace `AssistantCore`, does not bypass the permission broker or confirmation system, does not add autonomous behavior, and does not add desktop/browser automation or code execution.

Phase 34 adds an optional execution path through the agent runtime. `AssistantCore` keeps the existing direct path unless `AGENT_ENABLED=true`. When enabled, the same permission and confirmation controls still apply because the agent dispatches into the existing tool paths. The voice loop and GUI use the same toggle, and the agent remains experimental rather than autonomous.

Phase 35 adds a central health check that aggregates safe, read-only diagnostics across the existing configuration surface. It reports status only, never prints API keys or OAuth tokens, and does not change any command routing or backend capability. The health snapshot is available from the CLI and the GUI diagnostics tab.

Phase 36 adds packaging scaffolding for a future Windows build. It introduces runtime path resolution for source and packaged modes, a safe `--runtime-check` CLI report, a placeholder `build_exe.bat`, and packaging notes for a later PyInstaller phase. It does not build an EXE, install a startup service, or change Jarvis behavior.

Phase 37 adds only the first Windows PyInstaller build. It keeps the build console-enabled so packaged CLI diagnostics still work, includes whitelisted runtime assets when present, and does not add an installer, code signing, startup service, secrets, tokens, logs, or databases to the distribution.

Phase 38 adds packaged config bootstrap only. Source mode continues to use the project folder. Packaged mode uses `%APPDATA%\Jarvis` for writable logs, data, and credentials, and `%APPDATA%\Jarvis.env` for env settings copied from `.env.example` by `--init-config` only when missing.

Phase 39 adds only packaged launcher and smoke test scripts. It does not add an installer, code signing, startup registration, or microphone checks by default.

Phase 40 adds only optional current-user Windows startup registration. It writes at most one value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` after permission broker approval and explicit confirmation. It does not use `HKLM`, Task Scheduler, Windows services, admin permissions, elevation, installers, updaters, code signing, or autonomous behavior.
