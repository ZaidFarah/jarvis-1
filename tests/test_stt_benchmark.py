from __future__ import annotations

from pathlib import Path

import main as main_module
from config.settings import AppSettings
from voice.interfaces import TranscriptionResult
from voice.stt import write_wav_file
from voice.stt_benchmark import (
    STTBenchmarkProviderResult,
    STTBenchmarkReport,
    STTBenchmarkRunner,
    format_stt_benchmark_report,
)


def test_stt_benchmark_runs_providers_against_same_wav(tmp_path: Path) -> None:
    audio_path = write_wav_file(tmp_path / "sample.wav", [0.1, -0.1, 0.0], 16000)
    seen_paths: list[Path] = []

    class FakeProvider:
        name = "fake_file_stt"
        available = True

        def transcribe_file(self, path: Path) -> TranscriptionResult:
            seen_paths.append(Path(path))
            return TranscriptionResult(text="same sample", confidence=0.91, duration_seconds=0.5)

    times = iter([1.0, 1.125])
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    runner = STTBenchmarkRunner(
        settings,
        provider_builder=lambda: [FakeProvider()],
        clock=lambda: next(times),
    )

    report = runner.run(audio_path)

    assert seen_paths == [audio_path]
    assert report.audio_path == audio_path
    assert report.sample_rate == 16000
    assert report.input_device == "file"
    assert report.is_successful is True
    assert report.results[0].provider == "fake_file_stt"
    assert report.results[0].status == "ok"
    assert report.results[0].elapsed_ms == 125.0
    assert report.results[0].transcript == "same sample"


def test_stt_benchmark_records_once_to_logs_audio(tmp_path: Path) -> None:
    class FakeSoundDevice:
        default = type("Default", (), {"device": (3, None)})()

        def __init__(self) -> None:
            self.rec_calls: list[dict[str, object]] = []
            self.checked: list[dict[str, object]] = []

        def query_devices(self):
            return [{"name": "USB Mic", "max_input_channels": 1}]

        def check_input_settings(self, **kwargs) -> None:
            self.checked.append(kwargs)

        def rec(self, frames: int, **kwargs):
            self.rec_calls.append({"frames": frames, **kwargs})
            return [[0.1], [0.2], [0.0]]

        def wait(self) -> None:
            return None

    class FakeProvider:
        name = "fake_stt"
        available = True

        def transcribe_file(self, path: Path) -> TranscriptionResult:
            assert Path(path).exists()
            return TranscriptionResult(text="recorded once", confidence=0.8)

    sd = FakeSoundDevice()
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        voice_input_device="USB Mic",
        stt_benchmark_seconds=0.5,
    )
    runner = STTBenchmarkRunner(settings, provider_builder=lambda: [FakeProvider()], sounddevice_module=sd)

    report = runner.run()

    assert report.audio_path.parent == tmp_path / "logs" / "audio"
    assert report.audio_path.exists()
    assert report.input_device == "USB Mic (0)"
    assert sd.checked == [{"device": 0, "samplerate": 16000, "channels": 1}]
    assert sd.rec_calls == [
        {
            "frames": 8000,
            "samplerate": 16000,
            "channels": 1,
            "dtype": "float32",
            "device": 0,
        }
    ]
    assert report.results[0].transcript == "recorded once"


def test_stt_benchmark_skips_openai_without_api_key(tmp_path: Path, monkeypatch) -> None:
    audio_path = write_wav_file(tmp_path / "sample.wav", [0.0, 0.1], 16000)

    class FakeFasterWhisper:
        name = "faster_whisper"
        available = True

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def transcribe(self, samples, sample_rate: int) -> TranscriptionResult:
            del samples
            assert sample_rate == 16000
            return TranscriptionResult(text="local transcript", confidence=0.7)

    monkeypatch.setattr("voice.stt_benchmark.FasterWhisperSpeechToTextProvider", FakeFasterWhisper)
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs", openai_api_key="")

    report = STTBenchmarkRunner(settings).run(audio_path)

    assert [result.provider for result in report.results] == ["faster_whisper", "openai_stt"]
    assert report.results[0].status == "ok"
    assert report.results[1].status == "skipped"
    assert "OPENAI_API_KEY" in report.results[1].error


def test_stt_benchmark_report_formats_failures_and_transcripts() -> None:
    report = STTBenchmarkReport(
        audio_path=Path("logs/audio/sample.wav"),
        sample_rate=16000,
        audio_duration_seconds=5.0,
        input_device="file",
        results=(
            STTBenchmarkProviderResult(
                provider="faster_whisper",
                status="ok",
                elapsed_ms=42.5,
                transcript="run fast tests",
                confidence=0.93,
                audio_duration_seconds=5.0,
            ),
            STTBenchmarkProviderResult(
                provider="openai_stt",
                status="failed",
                elapsed_ms=12.0,
                error="RuntimeError: network failed",
            ),
        ),
    )

    text = format_stt_benchmark_report(report)

    assert "Jarvis STT Provider Benchmark" in text
    assert "audio file: logs\\audio\\sample.wav" in text or "audio file: logs/audio/sample.wav" in text
    assert "- faster_whisper: ok" in text
    assert "time: 42.5 ms" in text
    assert "confidence: 0.93" in text
    assert "transcript: run fast tests" in text
    assert "- openai_stt: failed" in text
    assert "RuntimeError: network failed" in text


def test_stt_benchmark_cli_uses_file_path(monkeypatch, capsys, tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, log_dir=tmp_path / "logs")
    report = STTBenchmarkReport(
        audio_path=Path("sample.wav"),
        sample_rate=16000,
        audio_duration_seconds=1.0,
        input_device="file",
        results=(
            STTBenchmarkProviderResult(
                provider="fake_stt",
                status="ok",
                elapsed_ms=1.0,
                transcript="hello",
            ),
        ),
    )
    seen_paths: list[str | None] = []

    class FakeRunner:
        def __init__(self, settings_arg: AppSettings) -> None:
            assert settings_arg is settings

        def run(self, audio_path: str | None = None) -> STTBenchmarkReport:
            seen_paths.append(audio_path)
            return report

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "STTBenchmarkRunner", FakeRunner)

    exit_code = main_module.main(["--stt-benchmark-file", "sample.wav"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert seen_paths == ["sample.wav"]
    assert "Jarvis STT Provider Benchmark" in output
    assert "fake_stt: ok" in output
