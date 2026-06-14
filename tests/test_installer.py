from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.installer import format_installer_check_report, run_installer_check
from main import main


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs")


def _write_installer_inputs(root: Path) -> None:
    (root / "dist" / "Jarvis").mkdir(parents=True)
    (root / "dist" / "Jarvis" / "Jarvis.exe").write_text("exe", encoding="utf-8")
    (root / "installer").mkdir(parents=True, exist_ok=True)
    (root / "installer" / "JarvisInstaller.iss").write_text(
        Path("installer/JarvisInstaller.iss").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "build_exe.bat").write_text("@echo off\n", encoding="utf-8")


def test_installer_script_exists_and_excludes_forbidden_sources() -> None:
    script = Path("installer/JarvisInstaller.iss").read_text(encoding="utf-8").lower()
    source_lines = "\n".join(line for line in script.splitlines() if line.strip().startswith("source:"))

    assert Path("installer/JarvisInstaller.iss").is_file()
    assert Path("build_installer.bat").is_file()
    assert "dist\\jarvis\\jarvis.exe" in script
    assert "dist\\jarvis\\_internal" in script
    assert ".env" not in source_lines
    assert "credentials" not in source_lines
    assert "token_" not in source_lines
    assert "logs/" not in source_lines
    assert "data/" not in source_lines
    assert ".git" not in source_lines


def test_installer_check_reports_expected_output_path(tmp_path: Path, monkeypatch) -> None:
    _write_installer_inputs(tmp_path)
    monkeypatch.setattr("diagnostics.installer.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("diagnostics.installer.shutil.which", lambda name: None)

    report = run_installer_check(_settings(tmp_path), project_root=tmp_path)
    text = format_installer_check_report(report)
    expected_output = tmp_path / "installer" / "output"

    assert report.output_dir == expected_output
    assert report.is_successful is True
    assert report.overall_status == "WARN"
    assert "Final installer readiness: WARN" in text
    assert str(expected_output) in text


def test_installer_check_command_runs_without_inno_setup(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_installer_inputs(tmp_path)
    monkeypatch.setattr("diagnostics.installer.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("diagnostics.installer.shutil.which", lambda name: None)
    monkeypatch.setattr("main.load_settings", lambda: _settings(tmp_path))

    exit_code = main(["--installer-check"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Installer Check" in output
    assert "Final installer readiness: WARN" in output


def test_installer_scripts_do_not_reference_secrets_or_hklm() -> None:
    installer_script = Path("installer/JarvisInstaller.iss").read_text(encoding="utf-8").lower()
    build_script = Path("build_installer.bat").read_text(encoding="utf-8").lower()

    combined = f"{installer_script}\n{build_script}"
    assert ".env" not in combined
    assert "credentials" not in combined
    assert "token_" not in combined
    assert "logs/" not in combined
    assert "data/" not in combined
    assert "hklm" not in combined
    assert "windows service" not in combined
    assert "service " not in combined
