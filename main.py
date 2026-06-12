from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.application import JarvisApplication
from assistant.core import AssistantCore, AssistantResponse
from config.settings import load_settings
from services.logging_service import configure_logging
from services.openai_service import OpenAIService, format_openai_check_report
from memory.store import SQLiteMemoryStore
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
    if "--audio-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = AudioDiagnostics(settings).run_full_check()
        print(format_audio_check_report(report))
        return 0 if report.is_successful else 1

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
            speak_requested=_has_flag(args, "--speak"),
            status_callback=_voice_command_status_callback,
        ).run()
        print(format_voice_command_report(report))
        return 0 if report.is_successful else 1

    if "--voice-loop" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        runner = VoiceLoopRunner(settings, status_callback=_voice_loop_status_callback)
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
        assistant = AssistantCore(settings=settings, openai_service=OpenAIService(settings))
        response = assistant.handle_command(message)
        tts_result = None
        if response.accepted and (settings.tts_enabled or _has_flag(args, "--speak")):
            tts_result = speak_text(response.text, settings, speak_requested=_has_flag(args, "--speak"))
        print(_format_chat_test_report(message, response, tts_result))
        return 0 if response.accepted and (tts_result is None or tts_result.spoken) else 1

    if "--chat-session" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        assistant = AssistantCore(settings=settings, openai_service=OpenAIService(settings))
        return _run_chat_session(assistant)

    if "--memory-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        return _run_memory_test(settings)

    application = JarvisApplication()
    return application.run()


def _chat_test_message(args: list[str]) -> str:
    inline_message = _message_after_flag(args, "--chat-test")
    if inline_message:
        return inline_message
    return input("You: ").strip()


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


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    sys.exit(main())
