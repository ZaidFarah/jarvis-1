from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.release_notes import format_release_notes_report, run_release_notes
from main import main


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs")


def test_release_notes_command_works(tmp_path: Path, monkeypatch, capsys) -> None:
    notes_dir = tmp_path / "releases"
    notes_dir.mkdir(parents=True)
    notes_path = notes_dir / "RELEASE_NOTES_0.1.0.md"
    notes_path.write_text("# Jarvis v0.1.0 Release Notes\n## Known Limitations\n- Unsigned EXE.\n", encoding="utf-8")
    monkeypatch.setattr("diagnostics.release_notes.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("main.load_settings", lambda: _settings(tmp_path))

    exit_code = main(["--release-notes"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Release Notes" in output
    assert "v0.1.0" in output
    assert "Known Limitations" in output


def test_changelog_exists() -> None:
    assert Path("CHANGELOG.md").is_file()


def test_release_notes_include_version_and_limitations(tmp_path: Path, monkeypatch) -> None:
    notes_dir = tmp_path / "releases"
    notes_dir.mkdir(parents=True)
    notes_path = notes_dir / "RELEASE_NOTES_0.1.0.md"
    notes_path.write_text(Path("releases/RELEASE_NOTES_0.1.0.md").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr("diagnostics.release_notes.PROJECT_ROOT", tmp_path)

    report = run_release_notes(_settings(tmp_path), project_root=tmp_path)
    text = format_release_notes_report(report)

    assert "Jarvis v0.1.0 Release Notes" in text
    assert "Known Limitations" in text
    assert "EXE and installer are unsigned" in text
    assert "Code signing is not enabled yet" in text


def test_release_notes_do_not_print_secrets(tmp_path: Path, monkeypatch) -> None:
    notes_dir = tmp_path / "releases"
    notes_dir.mkdir(parents=True)
    notes_path = notes_dir / "RELEASE_NOTES_0.1.0.md"
    notes_path.write_text("No secrets here.\n", encoding="utf-8")
    monkeypatch.setattr("diagnostics.release_notes.PROJECT_ROOT", tmp_path)

    report = run_release_notes(_settings(tmp_path), project_root=tmp_path)
    text = format_release_notes_report(report)

    assert "sk-" not in text
    assert "token_" not in text
    assert "client_secret" not in text
