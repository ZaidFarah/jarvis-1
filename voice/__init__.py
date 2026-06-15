"""Voice foundation package for Jarvis Phase 2."""

from voice.audio_diagnostics import AudioDiagnostics, AudioDiagnosticsReport, MicrophoneTestResult
from voice.command_capture import CommandCaptureDiagnosticRunner, CommandCaptureReport
from voice.command_validation import CommandValidationResult
from voice.interfaces import SpeechToTextProvider, TextToSpeechProvider, VoiceActivityDetector
from voice.transcription_diagnostics import TranscriptionDiagnostics, TranscriptionDiagnosticReport
from voice.voice_command_test import VoiceCommandTestReport, VoiceCommandTestRunner
from voice.voice_loop import VoiceLoopCycleReport, VoiceLoopRunner
from voice.wake import WakeDetectionResult, WakeDetector
from voice.wake_diagnostics import WakeDiagnosticReport, WakeDiagnostics

__all__ = [
    "AudioDiagnostics",
    "AudioDiagnosticsReport",
    "CommandCaptureDiagnosticRunner",
    "CommandCaptureReport",
    "CommandValidationResult",
    "MicrophoneTestResult",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "TranscriptionDiagnostics",
    "TranscriptionDiagnosticReport",
    "VoiceActivityDetector",
    "VoiceCommandTestReport",
    "VoiceCommandTestRunner",
    "VoiceLoopCycleReport",
    "VoiceLoopRunner",
    "WakeDetectionResult",
    "WakeDetector",
    "WakeDiagnosticReport",
    "WakeDiagnostics",
]
