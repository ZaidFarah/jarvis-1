"""Voice foundation package for Jarvis Phase 2."""

from voice.audio_diagnostics import AudioDiagnostics, AudioDiagnosticsReport, MicrophoneTestResult
from voice.interfaces import SpeechToTextProvider, TextToSpeechProvider, VoiceActivityDetector
from voice.transcription_diagnostics import TranscriptionDiagnostics, TranscriptionDiagnosticReport
from voice.wake import WakeDetectionResult, WakeDetector
from voice.wake_diagnostics import WakeDiagnosticReport, WakeDiagnostics

__all__ = [
    "AudioDiagnostics",
    "AudioDiagnosticsReport",
    "MicrophoneTestResult",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "TranscriptionDiagnostics",
    "TranscriptionDiagnosticReport",
    "VoiceActivityDetector",
    "WakeDetectionResult",
    "WakeDetector",
    "WakeDiagnosticReport",
    "WakeDiagnostics",
]
