from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.wake_provider import format_wake_provider_check_report, run_wake_provider_check
from main import main
from voice.wake_provider import resolve_wake_provider


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs")


def test_default_wake_provider_is_openwakeword() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.wake_provider == "openwakeword"
    assert settings.wake_fallback_provider == "whisper_fuzzy"
    assert settings.openwakeword_enabled is True


def test_wake_provider_check_passes_for_default_whisper_fuzzy(tmp_path: Path) -> None:
    report = run_wake_provider_check(_settings(tmp_path))

    assert report.status in {"PASS", "WARN"}
    assert report.resolution.effective_provider in {"openwakeword", "whisper_fuzzy", "manual"}
    assert report.message


def test_wake_provider_resolution_falls_back_when_openwakeword_missing(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        wake_provider="openwakeword",
        openwakeword_enabled=True,
        openwakeword_model="hey.jarvis",
    )
    monkeypatch.setattr("voice.wake_provider.is_openwakeword_installed", lambda: False)

    resolution = resolve_wake_provider(settings)

    assert resolution.selected_provider == "openwakeword"
    assert resolution.openwakeword_enabled is True
    assert resolution.openwakeword_installed is False
    assert resolution.model_configured is True
    assert resolution.wake_fallback_provider == "whisper_fuzzy"
    assert resolution.fallback_enabled is True
    assert resolution.effective_provider == "whisper_fuzzy"
    assert resolution.openwakeword_available is False
    assert resolution.manual_mode_required is True


def test_wake_provider_check_reports_expected_fields(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr("voice.wake_provider.is_openwakeword_installed", lambda: False)

    report = run_wake_provider_check(settings)
    text = format_wake_provider_check_report(report)

    assert "Selected provider:" in text
    assert "OpenWakeWord enabled:" in text
    assert "OpenWakeWord installed:" in text
    assert "Model configured:" in text
    assert "Fallback provider:" in text
    assert "Fallback enabled:" in text
    assert "Effective provider:" in text
    assert "Manual mode required:" in text
    assert "Message:" in text
    assert report.is_successful is True


def test_wake_provider_cli_command_works(tmp_path: Path, monkeypatch, capsys) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr("main.load_settings", lambda: settings)
    monkeypatch.setattr("voice.wake_provider.is_openwakeword_installed", lambda: False)

    exit_code = main(["--wake-provider-check"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Wake Provider Check" in output
    assert "Selected provider:" in output
    assert "Effective provider:" in output


def test_wake_provider_does_not_crash_when_dependency_missing(tmp_path: Path, monkeypatch) -> None:
    settings = AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        wake_provider="openwakeword",
        openwakeword_enabled=True,
        openwakeword_model="hey.jarvis",
    )
    monkeypatch.setattr("voice.wake_provider.is_openwakeword_installed", lambda: False)

    resolution = resolve_wake_provider(settings)

    assert resolution.effective_provider == "whisper_fuzzy"
    assert resolution.openwakeword_available is False
    assert resolution.manual_mode_required is True
