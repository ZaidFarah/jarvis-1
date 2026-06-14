from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.release_check import format_release_check_report, run_release_check


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs", runtime_mode="source")


def _write_release_project(
    root: Path,
    *,
    include_scripts: bool = True,
    include_readme_sections: bool = True,
    include_startup_commands: bool = True,
) -> None:
    (root / "build_exe.bat").write_text("@echo off\n", encoding="utf-8")
    if include_scripts:
        (root / "run_jarvis.bat").write_text("@echo off\n", encoding="utf-8")
        (root / "run_jarvis_console.bat").write_text("@echo off\n", encoding="utf-8")
        (root / "test_packaged_app.bat").write_text("@echo off\n", encoding="utf-8")

    if include_startup_commands:
        main_text = '"--startup-check"\n"--startup-enable"\n"--startup-disable"\n'
    else:
        main_text = 'print("Jarvis")\n'
    (root / "main.py").write_text(main_text, encoding="utf-8")

    if include_readme_sections:
        readme = "# Jarvis\n\n## Setup\n\n## Run\n\n## Packaging\n"
    else:
        readme = "# Jarvis\n\n## Setup\n"
    (root / "README.md").write_text(readme, encoding="utf-8")


def _item(report, name: str):
    return next(item for item in report.items if item.name == name)


def test_release_check_detects_missing_exe_as_warn_not_fail(tmp_path: Path) -> None:
    _write_release_project(tmp_path)

    report = run_release_check(
        _settings(tmp_path),
        project_root=tmp_path,
        tracked_files=["README.md", "main.py", "build_exe.bat"],
    )
    text = format_release_check_report(report)

    assert _item(report, "Packaged EXE").status == "WARN"
    assert report.overall_status == "WARN"
    assert report.is_successful is True
    assert "Final release readiness: WARN" in text
    assert not (tmp_path / "dist" / "Jarvis" / "Jarvis.exe").exists()


def test_release_check_detects_tracked_secrets_and_generated_files(tmp_path: Path) -> None:
    _write_release_project(tmp_path)

    report = run_release_check(
        _settings(tmp_path),
        project_root=tmp_path,
        tracked_files=[
            ".env",
            "credentials/google_client_secret.json",
            "credentials/token_gmail.json",
            "logs/jarvis.log",
            "data/jarvis_memory.db",
        ],
    )

    assert _item(report, ".env not tracked").status == "FAIL"
    assert _item(report, "credentials not tracked").status == "FAIL"
    assert _item(report, "tokens not tracked").status == "FAIL"
    assert _item(report, "logs not tracked").status == "FAIL"
    assert _item(report, "data DB files not tracked").status == "FAIL"
    assert report.overall_status == "FAIL"
    assert report.is_successful is False


def test_release_check_detects_missing_required_scripts(tmp_path: Path) -> None:
    _write_release_project(tmp_path, include_scripts=False)

    report = run_release_check(
        _settings(tmp_path),
        project_root=tmp_path,
        tracked_files=["README.md", "main.py", "build_exe.bat"],
    )

    item = _item(report, "Packaged smoke scripts")
    assert item.status == "FAIL"
    assert "run_jarvis.bat" in item.details
    assert "test_packaged_app.bat" in item.details


def test_release_check_detects_readme_section_gaps(tmp_path: Path) -> None:
    _write_release_project(tmp_path, include_readme_sections=False)

    report = run_release_check(
        _settings(tmp_path),
        project_root=tmp_path,
        tracked_files=["README.md", "main.py", "build_exe.bat"],
    )

    item = _item(report, "README setup/run/build sections")
    assert item.status == "FAIL"
    assert "run" in item.details
    assert "build" in item.details


def test_release_check_detects_missing_startup_commands(tmp_path: Path) -> None:
    _write_release_project(tmp_path, include_startup_commands=False)

    report = run_release_check(
        _settings(tmp_path),
        project_root=tmp_path,
        tracked_files=["README.md", "main.py", "build_exe.bat"],
    )

    item = _item(report, "Startup CLI commands")
    assert item.status == "FAIL"
    assert "--startup-check" in item.details
    assert "--startup-enable" in item.details
    assert "--startup-disable" in item.details
