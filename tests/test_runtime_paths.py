from __future__ import annotations

import sys
from pathlib import Path

from config.settings import AppSettings
from diagnostics.health import HealthService
from jarvis_runtime.config_bootstrap import format_config_init_report, initialize_config
from jarvis_runtime.runtime_paths import format_runtime_check_report, resolve_runtime_paths


def test_source_runtime_path_resolution() -> None:
    settings = AppSettings(_env_file=None, runtime_mode="source")
    report = resolve_runtime_paths(settings)

    assert report.runtime_mode == "source"
    assert report.project_root.name == "Jarvis"
    assert report.config_root == report.project_root
    assert report.env_path.name == ".env"
    assert report.logs_path.name == "logs"
    assert report.data_path.name == "data"
    assert report.credentials_path.name == "credentials"
    assert report.assets_path.name == "assets"


def test_packaged_mode_simulation(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    executable_root = tmp_path / "dist" / "Jarvis"
    settings = AppSettings(_env_file=None, runtime_mode="packaged")
    report = resolve_runtime_paths(
        settings,
        base_dir=executable_root,
        executable_path=executable_root / "Jarvis.exe",
        appdata_base=appdata,
    )
    text = format_runtime_check_report(report)

    assert report.runtime_mode == "packaged"
    assert report.runtime_root == executable_root
    assert report.config_root == appdata / "Jarvis"
    assert report.env_path == appdata / "Jarvis.env"
    assert report.logs_path == appdata / "Jarvis" / "logs"
    assert report.data_path == appdata / "Jarvis" / "data"
    assert report.credentials_path == appdata / "Jarvis" / "credentials"
    assert report.executable_path.name == "Jarvis.exe"
    assert "packaged" in text.lower()
    assert "Config root:" in text


def test_packaged_assets_use_pyinstaller_bundle_dir(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    bundle_root = tmp_path / "_internal"
    bundled_assets = bundle_root / "assets"
    bundled_assets.mkdir(parents=True)
    settings = AppSettings(_env_file=None)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)

    report = resolve_runtime_paths(settings, executable_path=tmp_path / "Jarvis.exe", appdata_base=appdata)

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


def test_init_config_creates_packaged_folders_and_env(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    template = tmp_path / ".env.example"
    template.write_text("OPENAI_ENABLED=false\nOPENAI_API_KEY=\n", encoding="utf-8")

    result = initialize_config(appdata_base=appdata, template_path=template)

    assert result.env_created is True
    assert result.env_already_exists is False
    assert result.paths.config_root.is_dir()
    assert result.paths.logs_path.is_dir()
    assert result.paths.data_path.is_dir()
    assert result.paths.credentials_path.is_dir()
    assert result.paths.env_path.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")


def test_init_config_does_not_overwrite_existing_env(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    template = tmp_path / ".env.example"
    template.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    env_path = appdata / "Jarvis.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("OPENAI_API_KEY=keep-existing\n", encoding="utf-8")

    result = initialize_config(appdata_base=appdata, template_path=template)

    assert result.env_created is False
    assert result.env_already_exists is True
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=keep-existing\n"


def test_init_config_does_not_create_secrets(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    template = tmp_path / ".env.example"
    template.write_text("OPENAI_API_KEY=\nWEATHER_API_KEY=\n", encoding="utf-8")

    result = initialize_config(appdata_base=appdata, template_path=template)

    assert result.paths.credentials_path.is_dir()
    assert list(result.paths.credentials_path.iterdir()) == []
    assert "sk-" not in result.paths.env_path.read_text(encoding="utf-8")
    assert not (result.paths.credentials_path / "google_client_secret.json").exists()
    assert not (result.paths.credentials_path / "token_gmail.json").exists()
    assert not (result.paths.credentials_path / "token_calendar.json").exists()


def test_init_config_report_prints_config_location(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    template = tmp_path / ".env.example"
    template.write_text("OPENAI_API_KEY=\n", encoding="utf-8")

    result = initialize_config(appdata_base=appdata, template_path=template)
    text = format_config_init_report(result)

    assert "Config root:" in text
    assert str(appdata / "Jarvis") in text
    assert str(appdata / "Jarvis.env") in text
    assert "Secrets created: no" in text


def test_health_check_still_works_after_runtime_changes() -> None:
    settings = AppSettings(_env_file=None)
    report = HealthService(settings).run_check()

    assert report.is_successful is True
