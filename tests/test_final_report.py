from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from config.settings import AppSettings
from diagnostics.final_report import format_final_report, run_final_report
from main import main


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        log_dir=tmp_path / "logs",
        openai_api_key="sk-secret-value",
        weather_api_key="weather-secret-value",
    )


def _fake_runtime_paths(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        runtime_mode="source",
        project_root=root,
        runtime_root=root,
        config_root=root,
        executable_path=root / "python.exe",
        env_path=root / ".env",
        logs_path=root / "logs",
        data_path=root / "data",
        credentials_path=root / "credentials",
        assets_path=root / "assets",
    )


def _fake_health_report(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        is_successful=True,
        log_file=root / "logs" / "health.log",
        sections=[
            ("System", [("Runtime mode", "source"), ("Config root", str(root))]),
            ("OpenAI", [("Enabled", "no")]),
        ],
    )


def _fake_check_report(status: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        overall_status=status,
        items=[SimpleNamespace(name=name, status=status, message="ok", details=[])],
        is_successful=status != "FAIL",
    )


def _install_fakes(monkeypatch, root: Path) -> None:
    (root / "build_exe.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "dist" / "Jarvis").mkdir(parents=True, exist_ok=True)
    (root / "dist" / "Jarvis" / "Jarvis.exe").write_text("exe", encoding="utf-8")
    monkeypatch.setattr("diagnostics.final_report.PROJECT_ROOT", root)
    monkeypatch.setattr("diagnostics.final_report.resolve_runtime_paths", lambda settings, runtime_mode=None, base_dir=None: _fake_runtime_paths(root))
    monkeypatch.setattr("diagnostics.final_report.HealthService", lambda settings: SimpleNamespace(run_check=lambda: _fake_health_report(root)))
    monkeypatch.setattr("diagnostics.final_report.run_release_check", lambda settings, project_root=None: _fake_check_report("PASS", "Release"))
    monkeypatch.setattr(
        "diagnostics.final_report.run_installer_check",
        lambda settings, project_root=None: SimpleNamespace(
            overall_status="PASS",
            items=[SimpleNamespace(name="Installer", status="PASS", message="ok", details=[])],
            is_successful=True,
            installer_script=root / "installer" / "JarvisInstaller.iss",
            output_dir=root / "installer" / "output",
        ),
    )
    monkeypatch.setattr(
        "diagnostics.final_report.run_signing_check",
        lambda settings, project_root=None: SimpleNamespace(
            overall_status="PASS",
            items=[SimpleNamespace(name="Signing", status="PASS", message="ok", details=[])],
            is_successful=True,
            signing_script=root / "sign_exe.bat",
        ),
    )
    monkeypatch.setattr("diagnostics.final_report.build_release_package_plan", lambda settings, project_root=None: SimpleNamespace(
        output_path=root / "releases" / "Jarvis-0.1.0-windows.zip",
        excluded_patterns=[".env", "credentials/", "tokens", "logs/", "data/*.db", ".git/"],
    ))
    monkeypatch.setattr("diagnostics.final_report._latest_git_commit", lambda root: "abc123 phase 48")


def test_final_report_command_works(tmp_path: Path, monkeypatch, capsys) -> None:
    _install_fakes(monkeypatch, tmp_path)
    monkeypatch.setattr("main.load_settings", lambda: _settings(tmp_path))

    exit_code = main(["--final-report"])
    output = capsys.readouterr().out

    report_path = tmp_path / "reports" / "Jarvis-0.1.0-validation-report.md"
    assert exit_code == 0
    assert report_path.is_file()
    assert "Report written to:" in output
    assert "Summary:" in output
    assert str(report_path) in output


def test_final_report_contains_required_sections(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, tmp_path)

    report = run_final_report(_settings(tmp_path), project_root=tmp_path)
    text = format_final_report(report)

    required_sections = [
        "## Overview",
        "## Test Reminder",
        "## Build Status",
        "## Release ZIP Status",
        "## Runtime Check Status",
        "## Health Check Status",
        "## Release Check Status",
        "## Installer Check Status",
        "## Signing Check Status",
        "## Enabled / Disabled Features",
        "## Security Summary",
        "## Known Limitations",
    ]
    for section in required_sections:
        assert section in text


def test_final_report_does_not_print_secrets(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, tmp_path)

    report = run_final_report(_settings(tmp_path), project_root=tmp_path)
    text = format_final_report(report)

    assert "sk-secret-value" not in text
    assert "weather-secret-value" not in text
    assert "Permission broker present: yes" in text
    assert "Secrets not bundled: yes" in text


def test_final_report_path_is_under_reports(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, tmp_path)

    report = run_final_report(_settings(tmp_path), project_root=tmp_path)

    assert report.report_path.parent.name == "reports"
    assert report.report_path.parent == tmp_path / "reports"


def test_missing_release_zip_is_warn_not_crash(tmp_path: Path, monkeypatch) -> None:
    _install_fakes(monkeypatch, tmp_path)

    report = run_final_report(_settings(tmp_path), project_root=tmp_path)
    text = format_final_report(report)

    assert report.overall_status == "WARN"
    assert "## Release ZIP Status" in text
    assert "ZIP exists: no" in text
