from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from diagnostics.signing import format_signing_check_report, run_signing_check
from main import main


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path / "logs")


def _write_signing_inputs(root: Path) -> None:
    (root / "dist" / "Jarvis").mkdir(parents=True)
    (root / "dist" / "Jarvis" / "Jarvis.exe").write_text("exe", encoding="utf-8")
    (root / "installer" / "output").mkdir(parents=True)
    (root / "installer" / "output" / "Jarvis-0.1.0-windows-installer.exe").write_text("installer", encoding="utf-8")
    (root / "sign_exe.bat").write_text(Path("sign_exe.bat").read_text(encoding="utf-8"), encoding="utf-8")
    (root / "sign_installer.bat").write_text(Path("sign_installer.bat").read_text(encoding="utf-8"), encoding="utf-8")


def test_signing_check_works_without_signtool(tmp_path: Path, monkeypatch) -> None:
    _write_signing_inputs(tmp_path)
    monkeypatch.setattr("diagnostics.signing.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("diagnostics.signing.shutil.which", lambda name: None)

    report = run_signing_check(_settings(tmp_path), project_root=tmp_path)
    text = format_signing_check_report(report)

    assert report.is_successful is True
    assert report.overall_status == "WARN"
    assert "signtool available" in text
    assert "Signing ready: WARN" in text


def test_signing_disabled_returns_safe_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_signing_inputs(tmp_path)
    monkeypatch.setattr("diagnostics.signing.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("diagnostics.signing.shutil.which", lambda name: None)
    monkeypatch.setattr("main.load_settings", lambda: _settings(tmp_path))

    exit_code = main(["--signing-check"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Signing enabled" in output
    assert "Signing ready: WARN" in output


def test_signing_scripts_do_not_contain_passwords_or_secrets() -> None:
    sign_exe = Path("sign_exe.bat").read_text(encoding="utf-8").lower()
    sign_installer = Path("sign_installer.bat").read_text(encoding="utf-8").lower()
    combined = f"{sign_exe}\n{sign_installer}"

    assert "password" not in combined
    assert "secret" not in combined
    assert "pfx password" not in combined
    assert "certificate password" not in combined


def test_no_password_fields_exist_in_settings() -> None:
    field_names = [name.lower() for name in AppSettings.model_fields]
    assert not any("password" in name for name in field_names)
