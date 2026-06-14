from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.application import JarvisApplication
from agent.runtime import AgentRuntime
from assistant.core import AssistantCore, AssistantResponse
from diagnostics.health import HealthService, format_health_check_report
from config.settings import load_settings
from jarvis_runtime.config_bootstrap import format_config_init_error, format_config_init_report, initialize_config
from jarvis_runtime.runtime_paths import format_runtime_check_report, resolve_runtime_paths
from integrations.calendar_service import CalendarService, format_calendar_auth_report, format_calendar_check_report
from integrations.gmail_service import (
    GmailService,
    format_gmail_auth_report,
    format_gmail_check_report,
    format_gmail_draft_list_report,
    format_gmail_draft_report,
    format_gmail_send_draft_report,
    format_gmail_unread_report,
)
from integrations.weather_service import WeatherService, format_weather_check_report
from services.notification_service import NotificationService, format_notification_check_report
from services.logging_service import configure_logging
from services.openai_service import OpenAIService, format_openai_check_report
from services.startup_service import StartupService, format_startup_action_report, format_startup_check_report
from security.permissions import PermissionBroker, format_permission_check_report, format_permission_decision
from security.confirmation import ConfirmationResult, confirm_action_cli, format_confirmation_result
from tools.app_launcher import AppLauncher, format_app_launch_report, format_app_launcher_check_report, format_app_resolution_report
from tools.file_access import FileAccess, format_file_access_check_report, format_file_search_report, format_folder_listing_report
from tools.website_launcher import WebsiteLauncher, format_website_launcher_check_report, format_website_open_report
from vision.vision_service import (
    VisionService,
    format_ocr_result,
    format_screenshot_result,
    format_vision_analysis_result,
    format_vision_check_report,
)
from memory.store import SQLiteMemoryStore
from reminders.service import ReminderService
from reminders.scheduler import ReminderWatcher
from voice.audio_diagnostics import AudioDiagnostics, format_audio_check_report
from voice.tts import TextToSpeechResult, format_tts_result, speak_text
from voice.transcription_diagnostics import TranscriptionDiagnostics, format_transcription_report
from voice.voice_command_test import (
    COMMAND_PROMPT,
    LISTENING_FOR_COMMAND_PROMPT,
    VoiceCommandTestRunner,
    format_voice_command_report,
)
from voice.voice_loop import (
    RETURNING_TO_SLEEP_MESSAGE,
    VoiceLoopRunner,
    VOICE_LOOP_STARTED_MESSAGE,
    VOICE_LOOP_STOPPED_MESSAGE,
)
from voice.wake_diagnostics import WakeDiagnostics, format_wake_report


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--packaged-smoke-plan" in args:
        print(_format_packaged_smoke_plan())
        return 0

    if "--init-config" in args:
        try:
            result = initialize_config()
        except FileNotFoundError as error:
            print(format_config_init_error(error))
            return 1
        print(format_config_init_report(result))
        return 0

    if "--audio-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = AudioDiagnostics(settings).run_full_check()
        print(format_audio_check_report(report))
        return 0 if report.is_successful else 1

    if "--health-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = HealthService(settings).run_check()
        print(format_health_check_report(report))
        return 0

    if "--runtime-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = resolve_runtime_paths(settings)
        print(format_runtime_check_report(report))
        return 0

    if "--startup-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = StartupService(settings).run_check()
        print(format_startup_check_report(report))
        return 0

    if "--startup-enable" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        result = StartupService(settings).enable_startup(_cli_confirmation_handler(settings))
        print(format_startup_action_report(result))
        return 0 if result.is_successful else 1

    if "--startup-disable" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        result = StartupService(settings).disable_startup(_cli_confirmation_handler(settings))
        print(format_startup_action_report(result))
        return 0 if result.is_successful else 1

    if "--transcribe-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = TranscriptionDiagnostics(settings).run_transcribe_test()
        print(format_transcription_report(report))
        return 0 if report.is_successful else 1

    if "--wake-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = WakeDiagnostics(settings).run_wake_test()
        print(format_wake_report(report))
        return 0 if report.is_successful else 1

    if "--voice-command-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = VoiceCommandTestRunner(
            settings,
            assistant=_build_cli_assistant(settings),
            speak_requested=_has_flag(args, "--speak"),
            status_callback=_voice_command_status_callback,
        ).run()
        print(format_voice_command_report(report))
        return 0 if report.is_successful else 1

    if "--voice-loop" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        runner = VoiceLoopRunner(settings, assistant=_build_cli_assistant(settings), status_callback=_voice_loop_status_callback)
        try:
            runner.run()
        except KeyboardInterrupt:
            runner.request_stop()
            print(runner.summary.format(), flush=True)
            print("\nJarvis voice loop interrupted. Exiting cleanly.", flush=True)
        return 0

    if "--openai-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = OpenAIService(settings).run_check()
        print(format_openai_check_report(report))
        return 0 if report.is_successful else 1

    if "--agent-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        user_input = _message_after_flag(args, "--agent-test")
        return _run_agent_test(settings, user_input)

    if "--agent-chat-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        user_input = _message_after_flag(args, "--agent-chat-test")
        return _run_agent_chat_test(settings, user_input)

    if "--notification-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = NotificationService(settings).run_check()
        print(format_notification_check_report(report))
        return 0 if report.is_successful else 1

    if "--notification-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        message = _message_after_flag(args, "--notification-test") or "Hello from Jarvis"
        return _run_notification_test(settings, message)

    if "--vision-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        PermissionBroker(settings).check("take screenshot", description="Vision diagnostic check.")
        report = VisionService(settings).run_check()
        print(format_vision_check_report(report))
        return 0 if report.is_successful else 1

    if "--vision-analyze" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        image_path = _message_after_flag(args, "--vision-analyze")
        return _run_vision_analyze(settings, image_path)

    if "--screenshot-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_screenshot_test(settings)

    if "--ocr-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        image_path = _message_after_flag(args, "--ocr-test")
        return _run_ocr_test(settings, image_path)

    if "--app-launcher-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = AppLauncher(settings).run_check()
        print(format_app_launcher_check_report(report))
        return 0 if report.is_successful else 1

    if "--resolve-app" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        app_name = _message_after_flag(args, "--resolve-app") or "notepad"
        result = AppLauncher(settings).resolve_only(app_name)
        print(format_app_resolution_report(result))
        return 0 if result.resolved_path else 1

    if "--launch-app" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        app_name = _message_after_flag(args, "--launch-app") or "notepad"
        return _run_launch_app(settings, app_name)

    if "--weather-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        PermissionBroker(settings).check(
            "weather query",
            description=f"Weather diagnostic for {settings.weather_default_city}.",
        )
        report = WeatherService(settings).run_check()
        print(format_weather_check_report(report))
        return 0 if report.is_successful else 1

    if "--calendar-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        PermissionBroker(settings).check(
            "read calendar",
            description="Calendar diagnostic for today.",
        )
        report = CalendarService(settings).run_check()
        print(format_calendar_check_report(report))
        return 0 if report.is_successful else 1

    if "--calendar-auth" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_calendar_auth(settings)

    if "--calendar-today" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_calendar_query(settings, "what is on my calendar today")

    if "--calendar-tomorrow" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_calendar_query(settings, "what is on my calendar tomorrow")

    if "--calendar-create" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        title, start_text, duration_minutes = _calendar_create_args(args)
        return _run_calendar_create(settings, title, start_text, duration_minutes)

    if "--gmail-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = GmailService(settings).run_check()
        print(format_gmail_check_report(report))
        return 0 if report.is_successful else 1

    if "--gmail-auth" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_gmail_auth(settings)

    if "--gmail-unread" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_gmail_unread(settings, speak_requested=_has_flag(args, "--speak"))

    if "--gmail-draft" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        recipient, subject, body = _gmail_draft_args(args)
        return _run_gmail_draft(settings, recipient, subject, body)

    if "--gmail-drafts" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_gmail_drafts(settings)

    if "--gmail-send-draft" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        draft_id = _message_after_flag(args, "--gmail-send-draft") or ""
        return _run_gmail_send_draft(settings, draft_id)

    if "--website-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = WebsiteLauncher(settings).run_check()
        print(format_website_launcher_check_report(report))
        return 0 if report.is_successful else 1

    if "--permission-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = PermissionBroker(settings).run_check()
        print(format_permission_check_report(report))
        return 0 if report.is_successful else 1

    if "--permission-check-action" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        action_name = _message_after_flag(args, "--permission-check-action") or "unknown action"
        decision = PermissionBroker(settings).check(action_name)
        print(format_permission_decision(decision))
        return 0 if decision.allowed else 1

    if "--confirm-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        action_name = _message_after_flag(args, "--confirm-test") or "read file contents"
        return _run_confirm_test(settings, action_name)

    if "--file-access-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = FileAccess(settings).run_check()
        print(format_file_access_check_report(report))
        return 0 if report.is_successful else 1

    if "--open-site" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        site_name = _message_after_flag(args, "--open-site") or "google"
        return _run_open_site(settings, site_name)

    if "--list-folder" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        folder_name = _message_after_flag(args, "--list-folder") or "documents"
        return _run_list_folder(settings, folder_name)

    if "--find-file" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        query, folder_name = _find_file_args(args)
        return _run_find_file(settings, query, folder_name)

    if "--read-file" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        filename, folder_name = _read_file_args(args)
        return _run_read_file(settings, filename, folder_name)

    if "--summarize-file" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        filename, folder_name = _read_file_args(args, flag="--summarize-file")
        return _run_summarize_file(settings, filename, folder_name)

    if "--tts-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        message = _message_after_flag(args, "--tts-test")
        result = speak_text(
            message,
            settings,
            speak_requested=True,
            provider_name=_flag_value(args, "--provider"),
        )
        print(format_tts_result(result))
        return 0 if result.spoken else 1

    if "--chat-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        message = _chat_test_message(args)
        assistant = _build_cli_assistant(settings)
        response = assistant.handle_command(message)
        tts_result = None
        if response.accepted and (settings.tts_enabled or _has_flag(args, "--speak")):
            tts_result = speak_text(response.text, settings, speak_requested=_has_flag(args, "--speak"))
        print(_format_chat_test_report(message, response, tts_result))
        return 0 if response.accepted and (tts_result is None or tts_result.spoken) else 1

    if "--chat-session" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        assistant = _build_cli_assistant(settings)
        return _run_chat_session(assistant)

    if "--memory-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_memory_test(settings)

    if "--reminders-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_reminders_test(settings)

    if "--reminders-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_reminders_check(settings, speak_requested=_has_flag(args, "--speak"))

    if "--reminders-watch" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_reminders_watch(settings, speak_requested=_has_flag(args, "--speak"))

    application = JarvisApplication()
    return application.run()


def _chat_test_message(args: list[str]) -> str:
    inline_message = _message_after_flag(args, "--chat-test")
    if inline_message:
        return inline_message
    return input("You: ").strip()


def _format_packaged_smoke_plan() -> str:
    return "\n".join(
        [
            "Jarvis Packaged Smoke Plan",
            "===========================",
            "After building the EXE, run these checks:",
            "",
            "1. cmd /c build_exe.bat",
            "2. dist\\Jarvis\\Jarvis.exe --init-config",
            "3. dist\\Jarvis\\Jarvis.exe --runtime-check",
            "4. dist\\Jarvis\\Jarvis.exe --health-check",
            "5. dist\\Jarvis\\Jarvis.exe --openai-check",
            "6. cmd /c test_packaged_app.bat",
            "7. run_jarvis_console.bat",
            "8. run_jarvis.bat",
            "",
            "Optional microphone check:",
            "  cmd /c test_packaged_app.bat --voice-command-test",
            "",
            "Do not run microphone checks by default.",
            "Packaged config lives under %APPDATA%\\Jarvis and %APPDATA%\\Jarvis.env.",
        ]
    )


def _message_after_flag(args: list[str], flag: str) -> str:
    index = args.index(flag)
    values: list[str] = []
    for value in args[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    return " ".join(values).strip()


def _has_flag(args: list[str], flag: str) -> bool:
    return flag in args


def _flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None

    index = args.index(flag)
    if index + 1 >= len(args):
        return None

    value = args[index + 1]
    if value.startswith("--"):
        return None
    return value


def _voice_command_status_callback(status: str) -> None:
    if status in {COMMAND_PROMPT, LISTENING_FOR_COMMAND_PROMPT}:
        print(status, flush=True)


def _voice_loop_status_callback(status: str) -> None:
    visible_statuses = {
        VOICE_LOOP_STARTED_MESSAGE,
        "Sleeping",
        "Listening for wake phrase",
        "Wake detected",
        COMMAND_PROMPT,
        LISTENING_FOR_COMMAND_PROMPT,
        "I didn't catch that.",
        RETURNING_TO_SLEEP_MESSAGE,
        "Stop command detected. Exiting voice loop.",
        "Thinking",
        "Speaking",
        VOICE_LOOP_STOPPED_MESSAGE,
    }
    visible_prefixes = ("Last recognized command:", "Last Jarvis response:", "Voice loop summary:")
    if status in visible_statuses or status.startswith(visible_prefixes):
        print(status, flush=True)


def _reminder_watch_status_callback(status: str) -> None:
    visible_statuses = {
        "Reminder watcher started.",
        "Reminder watcher stopped.",
        "Reminder watcher is disabled.",
        "Checking reminders...",
        "No reminders are due right now.",
        "Due reminders:",
    }
    visible_prefixes = ("Reminder watcher summary:", "Reminder watcher failed:")
    if status in visible_statuses or status.startswith(visible_prefixes):
        print(status, flush=True)


def _run_chat_session(assistant: AssistantCore) -> int:
    print("Jarvis chat session started. Type exit, quit, or bye to leave.", flush=True)
    try:
        while True:
            user_text = input("You: ").strip()
            if not user_text:
                continue

            if user_text.lower() in {"exit", "quit", "bye"}:
                print("Jarvis: Session closed.", flush=True)
                return 0

            response = assistant.handle_command(user_text)
            print(f"Jarvis: {response.text}", flush=True)
    except KeyboardInterrupt:
        print("\nJarvis chat session interrupted. Exiting cleanly.", flush=True)
        return 0


def _run_memory_test(settings) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_path = Path(temp_dir) / "jarvis_memory_test.db"
        store = SQLiteMemoryStore(memory_path)
        test_settings = settings.model_copy(
            update={
                "memory_enabled": True,
                "memory_database_path": memory_path,
                "openai_enabled": False,
            }
        )
        assistant = AssistantCore(settings=test_settings, memory_store=store)

        print("Jarvis memory test", flush=True)
        print(f"memory database: {memory_path}", flush=True)

        remember_response = assistant.handle_command("remember that the office code is blue")
        print(f"remember: {remember_response.text}", flush=True)

        list_response = assistant.handle_command("what do you remember")
        print("remembered:", flush=True)
        print(list_response.text, flush=True)

        forget_response = assistant.handle_command("forget that the office code is blue")
        print(f"forget: {forget_response.text}", flush=True)

        reset_response = assistant.handle_command("reset memory")
        print(f"reset: {reset_response.text}", flush=True)
        return 0


def _run_reminders_test(settings) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        reminders_path = Path(temp_dir) / "jarvis_reminders_test.db"
        test_settings = settings.model_copy(
            update={
                "reminders_enabled": True,
                "reminders_database_path": reminders_path,
                "openai_enabled": False,
            }
        )
        service = ReminderService(test_settings)
        assistant = AssistantCore(settings=test_settings, reminder_service=service)

        print("Jarvis reminders test", flush=True)
        print(f"reminders database: {reminders_path}", flush=True)

        invalid_response = assistant.handle_command("remind me to stretch")
        print(f"invalid time: {invalid_response.text}", flush=True)

        create_response = assistant.handle_command("remind me to stretch at 2026-06-12 18:30")
        print(f"create: {create_response.text}", flush=True)

        list_response = assistant.handle_command("list reminders")
        print("reminders:", flush=True)
        print(list_response.text, flush=True)

        complete_response = assistant.handle_command("complete reminder 1")
        print(f"complete: {complete_response.text}", flush=True)

        cancel_response = assistant.handle_command("cancel reminder 1")
        print(f"cancel: {cancel_response.text}", flush=True)
        return 0


def _run_reminders_check(settings, speak_requested: bool) -> int:
    reminder_service = ReminderService(settings) if settings.reminders_enabled else None
    assistant = AssistantCore(settings=settings, openai_service=OpenAIService(settings), reminder_service=reminder_service)
    response = assistant.handle_command("check reminders")
    tts_result = None
    should_speak = speak_requested or settings.reminders_speak_due or settings.tts_enabled
    if response.accepted and should_speak:
        tts_result = speak_text(response.text, settings, speak_requested=should_speak)

    print(_format_reminders_check_report(response, tts_result), flush=True)
    return 0 if response.accepted and (tts_result is None or tts_result.spoken) else 1


def _run_reminders_watch(settings, speak_requested: bool) -> int:
    watcher = ReminderWatcher(
        settings=settings,
        speak_requested=speak_requested,
        status_callback=_reminder_watch_status_callback,
    )
    if not watcher.available:
        print("Reminder watcher is disabled.", flush=True)
        return 0

    try:
        watcher.run_forever()
    except KeyboardInterrupt:
        watcher.stop()
        print("\nJarvis reminder watcher interrupted. Exiting cleanly.", flush=True)
    finally:
        print(watcher.summary.format(), flush=True)
    return 0


def _run_notification_test(settings, message: str) -> int:
    PermissionBroker(settings).check("show notification", description=f"Show notification with title Jarvis and message {message}.")
    result = NotificationService(settings).send_notification("Jarvis", message)
    print(format_notification_check_report(result), flush=True)
    return 0 if result.delivered else 1


def _run_screenshot_test(settings) -> int:
    service = VisionService(settings, confirmation_handler=_cli_confirmation_handler(settings), openai_service=OpenAIService(settings))
    result = service.capture_screenshot()
    print(format_screenshot_result(result), flush=True)
    return 0 if result.success else 1


def _run_ocr_test(settings, image_path: str) -> int:
    if not image_path:
        print("Please provide an image path for OCR.", flush=True)
        return 1
    service = VisionService(settings, confirmation_handler=_cli_confirmation_handler(settings), openai_service=OpenAIService(settings))
    result = service.ocr_image(image_path)
    print(format_ocr_result(result), flush=True)
    return 0 if result.success else 1


def _run_agent_test(settings, user_input: str) -> int:
    if not user_input:
        print("Please provide an agent test input.", flush=True)
        return 1
    runtime = AgentRuntime(settings=settings)
    result = runtime.run(user_input)
    print(_format_agent_test_report(result), flush=True)
    return 0 if result.final_response else 1


def _run_agent_chat_test(settings, user_input: str) -> int:
    if not user_input:
        print("Please provide an agent chat test input.", flush=True)
        return 1
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command(user_input)
    print(_format_agent_chat_test_report(user_input, response, settings.agent_enabled), flush=True)
    return 0 if response.accepted else 1


def _run_vision_analyze(settings, image_path: str) -> int:
    if not image_path:
        print("Please provide an image path for vision analysis.", flush=True)
        return 1
    service = VisionService(
        settings,
        confirmation_handler=_cli_confirmation_handler(settings),
        openai_service=OpenAIService(settings),
    )
    result = service.analyze_image(image_path)
    print(format_vision_analysis_result(result), flush=True)
    return 0 if result.success else 1


def _run_confirm_test(settings, action_name: str) -> int:
    broker = PermissionBroker(settings)
    decision = broker.check(action_name)
    if not decision.allowed:
        print(format_permission_decision(decision), flush=True)
        return 1

    if not decision.requires_confirmation:
        result = ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="No confirmation required.",
            log_file=settings.log_dir / "confirmations.log",
        )
        print(format_confirmation_result(result), flush=True)
        return 0

    result = confirm_action_cli(
        settings,
        decision.description,
        timeout_seconds=settings.confirmation_timeout_seconds,
        output_func=print,
    )
    print(format_confirmation_result(result), flush=True)
    return 0 if result.approved else 1


def _run_launch_app(settings, app_name: str) -> int:
    PermissionBroker(settings).check("open whitelisted app", description=f"Launch local app {app_name}.")
    result = AppLauncher(settings).launch_app(app_name)
    print(format_app_launch_report(result), flush=True)
    return 0 if result.request_attempted or result.launched else 1


def _run_open_site(settings, site_name: str) -> int:
    PermissionBroker(settings).check("open whitelisted website", description=f"Open site {site_name}.")
    result = WebsiteLauncher(settings).open_site(site_name)
    print(format_website_open_report(result), flush=True)
    return 0 if result.request_attempted or result.opened else 1


def _run_list_folder(settings, folder_name: str) -> int:
    PermissionBroker(settings).check(
        "list whitelisted folder filenames",
        description=f"List files in {folder_name}.",
    )
    result = FileAccess(settings).list_folder(folder_name)
    print(format_folder_listing_report(result), flush=True)
    return 0 if result.safe_error is None else 1


def _run_find_file(settings, query: str, folder_name: str) -> int:
    PermissionBroker(settings).check(
        "list whitelisted folder filenames",
        description=f"Search files in {folder_name} for {query}.",
    )
    result = FileAccess(settings).find_file(query, folder_name)
    print(format_file_search_report(result), flush=True)
    return 0 if result.request_attempted and result.safe_error is None else 1


def _run_read_file(settings, filename: str, folder_name: str) -> int:
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command(f"read file {filename} in {folder_name}")
    print(response.text, flush=True)
    return 0 if response.accepted else 1


def _run_summarize_file(settings, filename: str, folder_name: str) -> int:
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command(f"summarize file {filename} in {folder_name}")
    print(response.text, flush=True)
    return 0 if response.accepted else 1


def _run_calendar_auth(settings) -> int:
    report = CalendarService(settings).auth_calendar()
    print(format_calendar_auth_report(report), flush=True)
    return 0 if report.is_successful else 1


def _run_calendar_query(settings, command: str) -> int:
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command(command)
    print(response.text, flush=True)
    return 0 if response.accepted else 1


def _run_gmail_auth(settings) -> int:
    report = GmailService(settings).auth_gmail()
    print(format_gmail_auth_report(report), flush=True)
    return 0 if report.is_successful else 1


def _run_gmail_unread(settings, speak_requested: bool) -> int:
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command("read my unread emails")
    tts_result = None
    if response.accepted and (settings.tts_enabled or speak_requested):
        tts_result = speak_text(response.text, settings, speak_requested=speak_requested)
    print(_format_gmail_unread_report(response, tts_result), flush=True)
    return 0 if response.accepted and (tts_result is None or tts_result.spoken) else 1


def _run_gmail_draft(settings, recipient: str, subject: str, body: str) -> int:
    if not recipient or not subject or not body:
        print("Please provide a recipient, subject, and body.", flush=True)
        return 1
    assistant = _build_cli_assistant(settings)
    command = f"draft email to {recipient} subject {subject} body {body}"
    response = assistant.handle_command(command)
    print(_format_gmail_draft_report(response), flush=True)
    return 0 if response.accepted else 1


def _run_gmail_drafts(settings) -> int:
    assistant = _build_cli_assistant(settings)
    response = assistant.handle_command("list email drafts")
    print(_format_gmail_draft_list_report(response), flush=True)
    return 0 if response.accepted else 1


def _run_gmail_send_draft(settings, draft_id: str) -> int:
    if not draft_id:
        print("Please provide a Gmail draft ID.", flush=True)
        return 1
    assistant = _build_cli_assistant(settings)
    command = f"send email draft {draft_id}"
    response = assistant.handle_command(command)
    print(_format_gmail_send_draft_report(response), flush=True)
    return 0 if response.accepted else 1


def _run_calendar_create(settings, title: str, start_text: str, duration_minutes: int) -> int:
    if not title or not start_text or duration_minutes <= 0:
        print("Please provide a title, datetime in YYYY-MM-DD HH:MM format, and a positive duration.", flush=True)
        return 1
    assistant = _build_cli_assistant(settings)
    command = f"create calendar event {title} at {start_text} for {duration_minutes}"
    response = assistant.handle_command(command)
    print(response.text, flush=True)
    return 0 if response.accepted else 1


def _find_file_args(args: list[str]) -> tuple[str, str]:
    index = args.index("--find-file")
    values: list[str] = []
    for value in args[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    if not values:
        return "", "documents"
    if len(values) == 1:
        return values[0], "documents"
    return " ".join(values[:-1]).strip(), values[-1].strip()


def _read_file_args(args: list[str], flag: str = "--read-file") -> tuple[str, str]:
    index = args.index(flag)
    values: list[str] = []
    for value in args[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    if not values:
        return "", "documents"
    if len(values) == 1:
        return values[0], "documents"
    return " ".join(values[:-1]).strip(), values[-1].strip()


def _calendar_create_args(args: list[str]) -> tuple[str, str, int]:
    index = args.index("--calendar-create")
    values: list[str] = []
    for value in args[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    if len(values) < 3:
        return "", "", 0

    duration_text = values[-1]
    title_and_start = values[:-1]
    if len(title_and_start) >= 2 and _looks_like_calendar_datetime(title_and_start[-1]):
        title = " ".join(title_and_start[:-1]).strip()
        start_text = title_and_start[-1].strip()
    elif len(title_and_start) >= 3 and _looks_like_calendar_datetime(
        f"{title_and_start[-2]} {title_and_start[-1]}"
    ):
        title = " ".join(title_and_start[:-2]).strip()
        start_text = f"{title_and_start[-2]} {title_and_start[-1]}".strip()
    else:
        title = " ".join(title_and_start[:-1]).strip()
        start_text = title_and_start[-1].strip()

    try:
        duration_minutes = int(duration_text)
    except ValueError:
        duration_minutes = 0
    return title, start_text, duration_minutes


def _gmail_draft_args(args: list[str]) -> tuple[str, str, str]:
    index = args.index("--gmail-draft")
    values: list[str] = []
    for value in args[index + 1 :]:
        if value.startswith("--"):
            break
        values.append(value)
    if len(values) < 3:
        return "", "", ""
    recipient = values[0].strip()
    subject = values[1].strip()
    body = " ".join(values[2:]).strip()
    return recipient, subject, body


def _looks_like_calendar_datetime(value: str) -> bool:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return False
    try:
        from datetime import datetime

        for candidate in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                datetime.strptime(cleaned, candidate)
                return True
            except ValueError:
                continue
    except Exception:
        return False
    return False


def _format_chat_test_report(
    message: str,
    response: AssistantResponse,
    tts_result: TextToSpeechResult | None = None,
) -> str:
    lines = [
        "Jarvis Chat Test",
        "================",
        f"user: {message}",
        f"response source: {response.source}",
        "",
        "Jarvis response:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    if tts_result is not None:
        lines.extend(
            [
                "",
                "Text-to-speech:",
                f"  provider: {tts_result.provider_name}",
                f"  requested provider: {tts_result.requested_provider_name or tts_result.provider_name}",
                f"  provider available: {_yes_no(tts_result.provider_available)}",
                f"  fallback used: {_yes_no(tts_result.fallback_used)}",
                f"  spoken: {_yes_no(tts_result.spoken)}",
                f"  diagnostic log: {tts_result.log_file}",
            ]
        )
        if tts_result.audio_file:
            lines.append(f"  audio file: {tts_result.audio_file}")
        if tts_result.fallback_reason:
            lines.extend(["", "TTS fallback reason:", f"  {tts_result.fallback_reason}"])
        if tts_result.error:
            lines.extend(["", "TTS error:", f"  {tts_result.error}"])
    return "\n".join(lines)


def _format_reminders_check_report(
    response: AssistantResponse,
    tts_result: TextToSpeechResult | None = None,
) -> str:
    lines = [
        "Jarvis Reminders Check",
        "======================",
        f"response source: {response.source}",
        "",
        "Reminders result:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    if tts_result is not None:
        lines.extend(
            [
                "",
                "Text-to-speech:",
                f"  provider: {tts_result.provider_name}",
                f"  requested provider: {tts_result.requested_provider_name or tts_result.provider_name}",
                f"  provider available: {_yes_no(tts_result.provider_available)}",
                f"  fallback used: {_yes_no(tts_result.fallback_used)}",
                f"  spoken: {_yes_no(tts_result.spoken)}",
                f"  diagnostic log: {tts_result.log_file}",
            ]
        )
        if tts_result.audio_file:
            lines.append(f"  audio file: {tts_result.audio_file}")
        if tts_result.fallback_reason:
            lines.extend(["", "TTS fallback reason:", f"  {tts_result.fallback_reason}"])
        if tts_result.error:
            lines.extend(["", "TTS error:", f"  {tts_result.error}"])
    return "\n".join(lines)


def _format_agent_test_report(result) -> str:
    lines = [
        "Jarvis Agent Test",
        "=================",
        f"user: {result.user_input}",
        f"selected tool: {result.selected_tool}",
        f"reason: {result.reason}",
        "",
        "final response:",
        f"  {result.final_response}",
    ]
    if result.tool_result and result.tool_result != result.final_response:
        lines.extend(["", "tool result:", f"  {result.tool_result}"])
    if getattr(result.response, "error", None):
        lines.extend(["", "fallback reason:", f"  {result.response.error}"])
    return "\n".join(lines)


def _format_agent_chat_test_report(user_input: str, response: AssistantResponse, agent_enabled: bool) -> str:
    lines = [
        "Jarvis Agent Chat Test",
        "======================",
        f"user: {user_input}",
        f"agent enabled: {_yes_no(agent_enabled)}",
        f"response source: {response.source}",
        "",
        "Jarvis response:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    return "\n".join(lines)


def _format_gmail_unread_report(
    response: AssistantResponse,
    tts_result: TextToSpeechResult | None = None,
) -> str:
    lines = [
        "Jarvis Gmail Unread",
        "===================",
        f"response source: {response.source}",
        "",
        "Unread email summary:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    if tts_result is not None:
        lines.extend(
            [
                "",
                "Text-to-speech:",
                f"  provider: {tts_result.provider_name}",
                f"  requested provider: {tts_result.requested_provider_name or tts_result.provider_name}",
                f"  provider available: {_yes_no(tts_result.provider_available)}",
                f"  fallback used: {_yes_no(tts_result.fallback_used)}",
                f"  spoken: {_yes_no(tts_result.spoken)}",
                f"  diagnostic log: {tts_result.log_file}",
            ]
        )
        if tts_result.audio_file:
            lines.append(f"  audio file: {tts_result.audio_file}")
        if tts_result.fallback_reason:
            lines.extend(["", "TTS fallback reason:", f"  {tts_result.fallback_reason}"])
        if tts_result.error:
            lines.extend(["", "TTS error:", f"  {tts_result.error}"])
    return "\n".join(lines)


def _format_gmail_draft_report(response: AssistantResponse) -> str:
    lines = [
        "Jarvis Gmail Draft",
        "==================",
        f"response source: {response.source}",
        "",
        "Draft result:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    return "\n".join(lines)


def _format_gmail_draft_list_report(response: AssistantResponse) -> str:
    lines = [
        "Jarvis Gmail Drafts",
        "===================",
        f"response source: {response.source}",
        "",
        "Draft list result:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    return "\n".join(lines)


def _format_gmail_send_draft_report(response: AssistantResponse) -> str:
    lines = [
        "Jarvis Gmail Send Draft",
        "=======================",
        f"response source: {response.source}",
        "",
        "Send result:",
        f"  {response.text}",
    ]
    if response.error:
        lines.extend(["", "Fallback reason:", f"  {response.error}"])
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _build_cli_assistant(settings) -> AssistantCore:
    return AssistantCore(
        settings=settings,
        openai_service=OpenAIService(settings),
        confirmation_handler=_cli_confirmation_handler(settings),
    )


def _cli_confirmation_handler(settings):
    def _handler(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        del action_name, risk_level
        return confirm_action_cli(
            settings,
            description,
            timeout_seconds=settings.confirmation_timeout_seconds,
            output_func=print,
        )

    return _handler


if __name__ == "__main__":
    sys.exit(main())
