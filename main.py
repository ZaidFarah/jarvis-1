from __future__ import annotations

import sys

from app.application import JarvisApplication
from assistant.core import AssistantCore, AssistantResponse
from config.settings import load_settings
from services.logging_service import configure_logging
from services.openai_service import OpenAIService, format_openai_check_report
from voice.audio_diagnostics import AudioDiagnostics, format_audio_check_report
from voice.tts import TextToSpeechResult, format_tts_result, speak_text
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
        report = VoiceCommandTestRunner(settings, speak_requested=_has_flag(args, "--speak")).run()
        print(format_voice_command_report(report))
        return 0 if report.is_successful else 1

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
        result = speak_text(message, settings, speak_requested=True)
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
                f"  provider available: {_yes_no(tts_result.provider_available)}",
                f"  spoken: {_yes_no(tts_result.spoken)}",
                f"  diagnostic log: {tts_result.log_file}",
            ]
        )
        if tts_result.error:
            lines.extend(["", "TTS error:", f"  {tts_result.error}"])
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    sys.exit(main())
