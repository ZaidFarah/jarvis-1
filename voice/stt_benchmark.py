from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import AppSettings
from voice.fast_voice import resolve_fast_input_device
from voice.interfaces import TranscriptionResult
from voice.stt import (
    FasterWhisperSpeechToTextProvider,
    OpenAISpeechToTextProvider,
    read_wav_samples,
    transcribe_audio_file,
    write_wav_file,
)


@dataclass(frozen=True)
class STTBenchmarkProviderResult:
    provider: str
    status: str
    elapsed_ms: float
    transcript: str = ""
    confidence: float | None = None
    audio_duration_seconds: float | None = None
    error: str = ""

    @property
    def success(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True)
class STTBenchmarkReport:
    audio_path: Path
    sample_rate: int
    audio_duration_seconds: float
    input_device: str
    results: tuple[STTBenchmarkProviderResult, ...]

    @property
    def is_successful(self) -> bool:
        return any(result.success for result in self.results)


class STTBenchmarkRunner:
    """Record once, then transcribe the same WAV with each configured STT provider."""

    def __init__(
        self,
        settings: AppSettings,
        provider_builder: Callable[[], Sequence[Any]] | None = None,
        sounddevice_module: Any | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.settings = settings
        self.provider_builder = provider_builder
        self.sounddevice_module = sounddevice_module
        self.clock = clock

    def run(self, audio_path: str | Path | None = None) -> STTBenchmarkReport:
        if audio_path is None:
            saved_audio_path, input_device = self._record_benchmark_sample()
        else:
            saved_audio_path = Path(audio_path)
            input_device = "file"
            if not saved_audio_path.exists():
                raise FileNotFoundError(f"STT benchmark audio file was not found: {saved_audio_path}")

        samples, sample_rate = read_wav_samples(saved_audio_path)
        duration_seconds = len(samples) / sample_rate if sample_rate else 0.0
        results = list(self._run_provider_benchmarks(saved_audio_path))
        return STTBenchmarkReport(
            audio_path=saved_audio_path,
            sample_rate=sample_rate,
            audio_duration_seconds=duration_seconds,
            input_device=input_device,
            results=tuple(results),
        )

    def _record_benchmark_sample(self) -> tuple[Path, str]:
        sd = self.sounddevice_module or _require_sounddevice()
        device_index, device_name = resolve_fast_input_device(sd, self.settings.voice_input_device)
        sample_rate = self.settings.voice_sample_rate
        channels = self.settings.voice_channels
        seconds = self.settings.stt_benchmark_seconds
        frames = max(1, int(sample_rate * seconds))

        sd.check_input_settings(device=device_index, samplerate=sample_rate, channels=channels)
        recording = sd.rec(
            frames,
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            device=device_index,
        )
        sd.wait()

        audio_dir = self.settings.log_dir / "audio"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        audio_path = audio_dir / f"stt-benchmark-{timestamp}.wav"
        write_wav_file(audio_path, _recording_to_mono_samples(recording), sample_rate)
        return audio_path, f"{device_name} ({device_index})"

    def _run_provider_benchmarks(self, audio_path: Path) -> Sequence[STTBenchmarkProviderResult]:
        providers = list(self.provider_builder() if self.provider_builder is not None else self._default_providers())
        results: list[STTBenchmarkProviderResult] = []
        for provider in providers:
            results.append(self._run_single_provider(provider, audio_path))

        if self.provider_builder is None and not self.settings.has_openai_api_key:
            results.append(
                STTBenchmarkProviderResult(
                    provider="openai_stt",
                    status="skipped",
                    elapsed_ms=0.0,
                    error="OPENAI_API_KEY is not set; skipped.",
                )
            )
        return results

    def _default_providers(self) -> Sequence[Any]:
        providers: list[Any] = [
            FasterWhisperSpeechToTextProvider(
                model_name=self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        ]
        if self.settings.has_openai_api_key:
            providers.append(
                OpenAISpeechToTextProvider(
                    api_key=self.settings.openai_api_key,
                    model_name=self.settings.openai_stt_model,
                )
            )
        return providers

    def _run_single_provider(self, provider: Any, audio_path: Path) -> STTBenchmarkProviderResult:
        provider_name = str(getattr(provider, "name", provider.__class__.__name__))
        if not bool(getattr(provider, "available", False)):
            return STTBenchmarkProviderResult(
                provider=provider_name,
                status="failed",
                elapsed_ms=0.0,
                error=f"Provider '{provider_name}' is not available.",
            )

        started = self.clock()
        try:
            result: TranscriptionResult = transcribe_audio_file(provider, audio_path)
        except Exception as exc:
            return STTBenchmarkProviderResult(
                provider=provider_name,
                status="failed",
                elapsed_ms=(self.clock() - started) * 1000.0,
                error=f"{type(exc).__name__}: {exc}",
            )

        return STTBenchmarkProviderResult(
            provider=provider_name,
            status="ok",
            elapsed_ms=(self.clock() - started) * 1000.0,
            transcript=result.text.strip(),
            confidence=result.confidence,
            audio_duration_seconds=result.duration_seconds,
        )


def format_stt_benchmark_report(report: STTBenchmarkReport) -> str:
    lines = [
        "Jarvis STT Provider Benchmark",
        "=============================",
        f"audio file: {report.audio_path}",
        f"input: {report.input_device}",
        f"sample rate: {report.sample_rate}",
        f"audio duration: {report.audio_duration_seconds:.2f}s",
        "",
        "Results:",
    ]
    for result in report.results:
        confidence = "n/a" if result.confidence is None else f"{result.confidence:.2f}"
        duration = "n/a" if result.audio_duration_seconds is None else f"{result.audio_duration_seconds:.2f}s"
        lines.append(f"- {result.provider}: {result.status}")
        lines.append(f"  time: {result.elapsed_ms:.1f} ms")
        lines.append(f"  confidence: {confidence}")
        lines.append(f"  provider audio duration: {duration}")
        if result.transcript:
            lines.append(f"  transcript: {result.transcript}")
        else:
            lines.append("  transcript: <empty>")
        if result.error:
            lines.append(f"  error: {result.error}")
    return "\n".join(lines)


def _require_sounddevice() -> Any:
    try:
        return importlib.import_module("sounddevice")
    except Exception as exc:
        raise RuntimeError(f"sounddevice is required for STT benchmark recording: {exc}") from exc


def _recording_to_mono_samples(recording: Any) -> list[float]:
    if hasattr(recording, "tolist"):
        recording = recording.tolist()

    samples: list[float] = []
    for frame in recording:
        if isinstance(frame, (list, tuple)):
            if frame:
                samples.append(sum(float(value) for value in frame) / len(frame))
        else:
            samples.append(float(frame))
    return samples
