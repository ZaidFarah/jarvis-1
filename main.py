from __future__ import annotations

import sys

from app.application import JarvisApplication
from assistant.core import AssistantCore, AssistantResponse
from config.settings import load_settings
from services.logging_service import configure_logging
from services.openai_service import OpenAIService, format_openai_check_report
from voice.audio_diagnostics import AudioDiagnostics, format_audio_check_report
from voice.transcription_diagnostics import TranscriptionDiagnostics, format_transcription_report
from voice.voice_command_test import VoiceCommandTestRunner, format_voice_command_report
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
        report = VoiceCommandTestRunner(settings).run()
        print(format_voice_command_report(report))
        return 0 if report.is_successful else 1

    if "--openai-check" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        report = OpenAIService(settings).run_check()
        print(format_openai_check_report(report))
        return 0 if report.is_successful else 1

    if "--chat-test" in args:
        settings = load_settings()
        configure_logging(settings, console=False)
        message = _chat_test_message(args)
        assistant = AssistantCore(settings=settings, openai_service=OpenAIService(settings))
        response = assistant.handle_command(message)
        print(_format_chat_test_report(message, response))
        return 0 if response.accepted else 1

    application = JarvisApplication()
    return application.run()


def _chat_test_message(args: list[str]) -> str:
    index = args.index("--chat-test")
    inline_message = " ".join(args[index + 1 :]).strip()
    if inline_message:
        return inline_message
    return input("You: ").strip()


def _format_chat_test_report(message: str, response: AssistantResponse) -> str:
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
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
