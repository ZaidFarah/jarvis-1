from __future__ import annotations


class Pyttsx3TextToSpeechProvider:
    """Optional local placeholder TTS provider for Phase 2."""

    name = "pyttsx3"

    def __init__(self) -> None:
        try:
            import pyttsx3  # type: ignore[import-not-found]
        except Exception:
            self._pyttsx3 = None
        else:
            self._pyttsx3 = pyttsx3

    @property
    def available(self) -> bool:
        return self._pyttsx3 is not None

    def speak(self, text: str) -> None:
        if not self.available:
            raise RuntimeError("pyttsx3 is not available in this Python environment.")

        engine = self._pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
