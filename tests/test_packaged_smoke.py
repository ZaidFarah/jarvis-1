from __future__ import annotations

from pathlib import Path

from main import main


SCRIPT_NAMES = ["run_jarvis.bat", "run_jarvis_console.bat", "test_packaged_app.bat"]


def test_packaged_launcher_scripts_exist() -> None:
    for script_name in SCRIPT_NAMES:
        assert Path(script_name).is_file()


def test_packaged_smoke_plan_prints_required_checks(capsys) -> None:
    exit_code = main(["--packaged-smoke-plan"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Jarvis Packaged Smoke Plan" in output
    assert "dist\\Jarvis\\Jarvis.exe --init-config" in output
    assert "dist\\Jarvis\\Jarvis.exe --runtime-check" in output
    assert "dist\\Jarvis\\Jarvis.exe --health-check" in output
    assert "dist\\Jarvis\\Jarvis.exe --openai-check" in output
    assert "cmd /c test_packaged_app.bat" in output
    assert "run_jarvis.bat" in output
    assert "run_jarvis_console.bat" in output


def test_packaged_smoke_plan_marks_voice_command_test_optional(capsys) -> None:
    exit_code = main(["--packaged-smoke-plan"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Optional microphone check:" in output
    assert "test_packaged_app.bat --voice-command-test" in output
    assert "Do not run microphone checks by default." in output


def test_packaged_smoke_script_runs_voice_command_only_when_requested() -> None:
    script = Path("test_packaged_app.bat").read_text(encoding="utf-8")

    assert '"%EXE%" --runtime-check' in script
    assert '"%EXE%" --health-check' in script
    assert '"%EXE%" --openai-check' in script
    assert 'if /i "%~1"=="--voice-command-test"' in script
    assert 'Skipping voice command test. Pass --voice-command-test to enable it.' in script


def test_packaged_smoke_commands_do_not_include_secret_values(capsys) -> None:
    main(["--packaged-smoke-plan"])
    combined = [capsys.readouterr().out]
    combined.extend(Path(script_name).read_text(encoding="utf-8") for script_name in SCRIPT_NAMES)
    text = "\n".join(combined)

    forbidden = [
        "OPENAI_API_KEY=",
        "WEATHER_API_KEY=",
        "sk-",
        "google_client_secret.json",
        "token_gmail.json",
        "token_calendar.json",
    ]
    for secret_marker in forbidden:
        assert secret_marker not in text
