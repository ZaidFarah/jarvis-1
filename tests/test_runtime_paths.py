from __future__ import annotations

import sys
from pathlib import Path

from config.settings import AppSettings
from diagnostics.health import HealthService
from jarvis_runtime.runtime_paths import format_runtime_check_report, resolve_runtime_paths


def test_source_runtime_path_resolution() -> None:
    settings = AppSettings(_env_file=None, runtime_mode="source")
    report = resolve_runtime_paths(settings)

    assert report.runtime_mode == "source"
    assert report.project_root.name == "Jarvis"
    assert report.env_path.name == ".env"
    assert report.logs_path.name == "logs"
    assert report.data_path.name == "data"
    assert report.credentials_path.name == "credentials"
    assert report.assets_path.name == "assets"


def test_packaged_mode_simulation(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, runtime_mode="packaged")
    report = resolve_runtime_paths(settings, base_dir=tmp_path, executable_path=tmp_path / "Jarvis.exe")
    text = format_runtime_check_report(report)

    assert report.runtime_mode == "packaged"
    assert report.runtime_root == tmp_path
    assert report.executable_path.name == "Jarvis.exe"
    assert "packaged" in text.lower()


def test_packaged_assets_use_pyinstaller_bundle_dir(tmp_path: Path, monkeypatch) -> None:
    bundle_root = tmp_path / "_internal"
    bundled_assets = bundle_root / "assets"
    bundled_assets.mkdir(parents=True)
    settings = AppSettings(_env_file=None)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)

    report = resolve_runtime_paths(settings, executable_path=tmp_path / "Jarvis.exe")

    assert report.runtime_mode == "packaged"
    assert report.runtime_root == tmp_path
    assert report.assets_path == bundled_assets


def test_runtime_check_does_not_print_secrets() -> None:
    settings = AppSettings(
        _env_file=None,
        runtime_mode="source",
        openai_enabled=True,
        openai_api_key="sk-secret",
        gmail_enabled=True,
        calendar_enabled=True,
    )
    report = resolve_runtime_paths(settings)
    text = format_runtime_check_report(report)

    assert "sk-secret" not in text
    assert "token" not in text.lower()


def test_health_check_still_works_after_runtime_changes() -> None:
    settings = AppSettings(_env_file=None)
    report = HealthService(settings).run_check()

    assert report.is_successful is True
