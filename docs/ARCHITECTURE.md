# Jarvis Architecture

## Purpose

 Jarvis is being built as a production-quality Windows desktop assistant. Phase 1 created the safe desktop foundation. Phase 2 added a limited local voice foundation for microphone diagnostics and provider interfaces. Phase 2.5 improved diagnostic reliability and reporting. Phase 3 added one-shot Faster Whisper transcription testing. Phase 4 added controlled wake phrase detection as a test mode only. Phase 5 added a controlled one-shot voice command test mode. Phase 6 added OpenAI connection diagnostics. Phase 7 connects `AssistantCore` to OpenAI chat with local fallback. Phase 8 adds safe local text-to-speech for Jarvis responses. Phase 8.5 adds OpenAI TTS as the preferred voice provider with local `pyttsx3` fallback. Phase 8.6 improves one-shot command capture timing after wake detection. Phase 9 adds the first continuous voice loop. Phase 9.5 polishes that loop with spoken status feedback, cooldowns, summary counters, and richer GUI state. Phase 10 adds short-term in-memory conversation history for the current session. Phase 11 adds SQLite-backed persistent local memory for explicit user-approved facts only. Phase 12 adds safe weather lookups through OpenWeatherMap with explicit configuration and fallback handling. Phase 13 adds local SQLite reminders with simple explicit command routing. Phase 14 adds manual due-reminder checking and optional spoken reminder output. Phase 15 adds a local reminder watcher that runs only while Jarvis is active. Phase 16 adds optional Windows toast notifications. Phase 17 adds a safe local application launcher. Phase 18 adds a safe website launcher for whitelisted sites only. Phase 19 adds safe read-only file access for whitelisted folders only. Phase 20 adds a central permission broker that classifies sensitive actions before future confirmation flows exist. Phase 21 adds interactive confirmation for medium and high-risk actions. Phase 22 adds safe read-only file content reading for whitelisted folders with confirmation gating. Phase 23 adds safe file summarization for whitelisted text files with a second confirmation before OpenAI upload. Phase 24 adds a safe Google Calendar read-only foundation with confirmation-gated reads. Phase 25 adds Google Calendar OAuth setup and read-only event queries. Phase 36 adds packaging scaffolding with runtime path resolution and a safe runtime check without building the final executable.

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
- `memory/store.py`: manages SQLite persistence for explicit user-approved memories, rejects sensitive secrets, and supports remember/list/forget/reset operations.
- `integrations/weather_service.py`: performs explicit weather checks, fetches current weather only when enabled and keyed, redacts secret-like error text, and writes `logs/weather.log`.
- `reminders/service.py`: manages explicit reminder commands, parses simple time strings, routes to SQLite storage, and writes `logs/reminders.log`.
- `reminders/store.py`: persists reminders with title, remind_at, status, created_at, and updated_at fields.
- `reminders/scheduler.py`: runs the local reminder watcher loop, checks due reminders at the configured interval, and can speak due reminders while Jarvis is running.

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

Phase 9 has no tools, no startup background service, and no permissions system. It cannot access email, calendar, browser automation, desktop automation, memory, screenshots, or local file content. OpenAI usage is limited to plain text chat responses and text-to-speech from the user command text or assistant response. The OpenAI TTS voice direction is an original assistant voice: calm, mature, professional, British-inspired, deep but clear, slightly cinematic, and natural paced. It must not clone or imitate a real actor or copyrighted movie character.

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
