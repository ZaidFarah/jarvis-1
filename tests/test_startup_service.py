from __future__ import annotations

from pathlib import Path

from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from services.startup_service import (
    RUN_KEY_PATH,
    StartupService,
    format_startup_action_report,
    format_startup_check_report,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []

    def get_value(self, name: str) -> str | None:
        return self.values.get(name)

    def set_value(self, name: str, value: str) -> None:
        self.values[name] = value
        self.set_calls.append((name, value))

    def delete_value(self, name: str) -> None:
        self.values.pop(name, None)
        self.delete_calls.append(name)


def _settings(tmp_path: Path, **overrides) -> AppSettings:
    return AppSettings(_env_file=None, log_dir=tmp_path, **overrides)


def _approve(*args) -> ConfirmationResult:
    action_name, risk_level, description = args
    assert action_name in {"register startup", "unregister startup"}
    assert risk_level == "medium"
    assert description
    return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.")


def _deny(*args) -> ConfirmationResult:
    action_name, risk_level, description = args
    assert action_name in {"register startup", "unregister startup"}
    assert risk_level == "medium"
    assert description
    return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", errors=["Denied."])


def test_startup_check_disabled_and_not_registered(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    service = StartupService(
        _settings(tmp_path),
        registry=FakeRegistry(),
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    report = service.run_check()
    text = format_startup_check_report(report)

    assert report.supported is True
    assert report.startup_enabled_setting is False
    assert report.registered is False
    assert report.registry_key == f"HKCU\\{RUN_KEY_PATH}"
    assert "Startup supported: yes" in text


def test_startup_enable_requires_confirmation_and_registers_source_launcher(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    registry = FakeRegistry()
    service = StartupService(
        _settings(tmp_path),
        registry=registry,
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    result = service.enable_startup(_approve)
    text = format_startup_action_report(result)

    assert result.success is True
    assert result.changed is True
    assert registry.values["Jarvis"] == f'"{launcher.resolve()}"'
    assert "Confirmation required: yes" in text


def test_startup_enable_denied_confirmation_does_not_modify_registry(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    registry = FakeRegistry()
    service = StartupService(
        _settings(tmp_path),
        registry=registry,
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    result = service.enable_startup(_deny)

    assert result.success is False
    assert result.changed is False
    assert registry.values == {}
    assert registry.set_calls == []


def test_startup_disable_requires_confirmation_and_deletes_value(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    command = f'"{launcher.resolve()}"'
    registry = FakeRegistry()
    registry.values["Jarvis"] = command
    service = StartupService(
        _settings(tmp_path),
        registry=registry,
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    result = service.disable_startup(_approve)

    assert result.success is True
    assert result.changed is True
    assert "Jarvis" not in registry.values
    assert registry.delete_calls == ["Jarvis"]


def test_startup_disable_denied_confirmation_does_not_modify_registry(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    command = f'"{launcher.resolve()}"'
    registry = FakeRegistry()
    registry.values["Jarvis"] = command
    service = StartupService(
        _settings(tmp_path),
        registry=registry,
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    result = service.disable_startup(_deny)

    assert result.success is False
    assert result.changed is False
    assert registry.values["Jarvis"] == command
    assert registry.delete_calls == []


def test_startup_source_mode_targets_run_jarvis_bat(tmp_path: Path) -> None:
    launcher = tmp_path / "run_jarvis.bat"
    launcher.write_text("@echo off\n", encoding="utf-8")
    service = StartupService(
        _settings(tmp_path),
        registry=FakeRegistry(),
        runtime_mode="source",
        project_root=tmp_path,
        os_name="nt",
    )

    target = service.resolve_target()

    assert target.supported is True
    assert target.runtime_mode == "source"
    assert target.target_path == launcher.resolve()
    assert target.command == f'"{launcher.resolve()}"'


def test_startup_packaged_mode_targets_jarvis_exe(tmp_path: Path) -> None:
    exe = tmp_path / "dist" / "Jarvis" / "Jarvis.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    service = StartupService(
        _settings(tmp_path),
        registry=FakeRegistry(),
        runtime_mode="packaged",
        project_root=tmp_path,
        executable_path=exe,
        os_name="nt",
    )

    target = service.resolve_target()

    assert target.supported is True
    assert target.runtime_mode == "packaged"
    assert target.target_path == exe.resolve()
    assert target.command == f'"{exe.resolve()}"'


def test_startup_never_uses_hklm() -> None:
    source = Path("services/startup_service.py").read_text(encoding="utf-8")

    assert "HKEY_LOCAL_MACHINE" not in source
    assert "HKLM" not in source
