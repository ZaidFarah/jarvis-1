from __future__ import annotations

import re
from pathlib import Path

from config.settings import AppSettings
from jarvis_runtime.release_package import (
    build_release_package_plan,
    format_release_package_check_report,
    run_release_package_check,
)
from jarvis_runtime.version import APP_VERSION, format_version, is_valid_version
from main import main


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, app_version=APP_VERSION, log_dir=tmp_path / "logs")


def _write_package_inputs(root: Path) -> None:
    internal = root / "dist" / "Jarvis" / "_internal"
    internal.mkdir(parents=True)
    (internal / "runtime.txt").write_text("runtime", encoding="utf-8")
    (root / "dist" / "Jarvis" / "Jarvis.exe").write_text("exe", encoding="utf-8")
    (root / "README.md").write_text("# Jarvis\n", encoding="utf-8")
    (root / "run_jarvis.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "run_jarvis_console.bat").write_text("@echo off\n", encoding="utf-8")
    (root / "test_packaged_app.bat").write_text("@echo off\n", encoding="utf-8")


def test_version_command_works(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr("main.load_settings", lambda: _settings(tmp_path))

    exit_code = main(["--version"])
    output = capsys.readouterr().out.strip()

    assert exit_code == 0
    assert output == "Jarvis 0.1.0"


def test_version_string_format() -> None:
    assert is_valid_version(APP_VERSION)
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
    assert format_version("Jarvis", APP_VERSION) == "Jarvis 0.1.0"


def test_release_zip_plan_excludes_secrets(tmp_path: Path) -> None:
    plan = build_release_package_plan(_settings(tmp_path), project_root=tmp_path)
    combined = "\n".join(entry.archive_path for entry in plan.entries).lower()

    assert "dist/jarvis/jarvis.exe" in combined
    assert "dist/jarvis/_internal/" in combined
    assert ".env" not in combined
    assert "credentials" not in combined
    assert "token" not in combined
    assert "logs" not in combined
    assert "data" not in combined
    assert ".git" not in combined
    assert ".env" in plan.excluded_patterns
    assert "credentials/" in plan.excluded_patterns
    assert ".git/" in plan.excluded_patterns


def test_release_package_check_reports_expected_output_path(tmp_path: Path) -> None:
    _write_package_inputs(tmp_path)
    report = run_release_package_check(_settings(tmp_path), project_root=tmp_path)
    text = format_release_package_check_report(report)
    expected = tmp_path / "releases" / "Jarvis-0.1.0-windows.zip"

    assert report.is_successful is True
    assert report.plan.output_path == expected
    assert str(expected) in text
    assert "Final package readiness: PASS" in text
    assert not expected.exists()


def test_release_script_exists_and_does_not_stage_secrets() -> None:
    script = Path("create_release_zip.bat").read_text(encoding="utf-8").lower()
    copy_lines = "\n".join(line for line in script.splitlines() if line.strip().startswith(("copy ", "xcopy ")))

    assert "jarvis.exe" in script
    assert "_internal" in script
    assert "staging_dist" in script
    assert "readme.md" in script
    assert "run_jarvis.bat" in script
    assert "test_packaged_app.bat" in script
    assert ".env" not in copy_lines
    assert "credentials" not in copy_lines
    assert "token" not in copy_lines
    assert ".git" not in copy_lines
