from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import AppSettings, PROJECT_ROOT


@dataclass(frozen=True)
class SigningCheckItem:
    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SigningCheckReport:
    signing_script: Path
    items: list[SigningCheckItem] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        statuses = {item.status for item in self.items}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    @property
    def is_successful(self) -> bool:
        return self.overall_status != "FAIL"


def run_signing_check(settings: AppSettings, *, project_root: Path | None = None) -> SigningCheckReport:
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    signing_script = root / "sign_exe.bat"
    exe_path = root / "dist" / "Jarvis" / "Jarvis.exe"
    installer_path = _find_installer_path(root)
    signtool_path = _find_signtool()

    items = [
        _enabled_check(settings),
        _tool_check("signtool available", signtool_path, "Signtool is available.", "Signtool is not available locally."),
        _configuration_check(
            "certificate path configured",
            bool(settings.signing_cert_path.strip()),
            "A certificate path is configured.",
            "Set SIGNING_CERT_PATH to a certificate file path.",
            disabled_status="WARN",
        ),
        _configuration_check(
            "timestamp server configured",
            bool(settings.signing_timestamp_url.strip()),
            "A timestamp server is configured.",
            "Set SIGNING_TIMESTAMP_URL to a timestamp server URL.",
            disabled_status="WARN",
        ),
        _file_check("Packaged EXE", exe_path, "dist\\Jarvis\\Jarvis.exe exists.", "dist\\Jarvis\\Jarvis.exe is missing."),
        _installer_check(installer_path),
        _safe_script_check(signing_script),
    ]
    items.append(_readiness_check(settings, items))
    return SigningCheckReport(signing_script=signing_script, items=items)


def format_signing_check_report(report: SigningCheckReport) -> str:
    lines = [
        "Jarvis Signing Check",
        "====================",
        f"Signing script: {report.signing_script}",
    ]
    for item in report.items:
        lines.append(f"{item.status} | {item.name}: {item.message}")
        lines.extend(f"  - {detail}" for detail in item.details)
    lines.extend(["", f"Signing ready: {report.overall_status}"])
    return "\n".join(lines)


def _enabled_check(settings: AppSettings) -> SigningCheckItem:
    if settings.signing_enabled:
        return SigningCheckItem(
            name="Signing enabled",
            status="PASS",
            message="Signing is enabled.",
        )
    return SigningCheckItem(
        name="Signing enabled",
        status="WARN",
        message="Signing is disabled. No signing action will run.",
    )


def _tool_check(name: str, tool_path: Path | None, pass_message: str, warn_message: str) -> SigningCheckItem:
    if tool_path is not None:
        return SigningCheckItem(name=name, status="PASS", message=pass_message, details=[str(tool_path)])
    return SigningCheckItem(name=name, status="WARN", message=warn_message)


def _configuration_check(
    name: str,
    configured: bool,
    pass_message: str,
    fail_message: str,
    *,
    disabled_status: str,
) -> SigningCheckItem:
    if configured:
        return SigningCheckItem(name=name, status="PASS", message=pass_message)
    return SigningCheckItem(name=name, status=disabled_status, message=fail_message)


def _file_check(name: str, path: Path, pass_message: str, fail_message: str) -> SigningCheckItem:
    if path.is_file():
        return SigningCheckItem(name=name, status="PASS", message=pass_message, details=[str(path)])
    return SigningCheckItem(name=name, status="WARN", message=fail_message, details=[str(path)])


def _installer_check(installer_path: Path | None) -> SigningCheckItem:
    if installer_path is None:
        return SigningCheckItem(
            name="Installer",
            status="WARN",
            message="Installer output is not present yet.",
        )
    return SigningCheckItem(name="Installer", status="PASS", message="Installer output exists.", details=[str(installer_path)])


def _safe_script_check(script_path: Path) -> SigningCheckItem:
    if not script_path.is_file():
        return SigningCheckItem(
            name="Signing script",
            status="FAIL",
            message="sign_exe.bat is missing.",
            details=[str(script_path)],
        )
    text = script_path.read_text(encoding="utf-8").lower()
    forbidden = [token for token in ("password", "secret", "/p ", "pfx password") if token in text]
    if forbidden:
        return SigningCheckItem(
            name="Signing script",
            status="FAIL",
            message="Signing script contains forbidden secret references.",
            details=forbidden,
        )
    return SigningCheckItem(name="Signing script", status="PASS", message="Signing script does not contain secret references.")


def _readiness_check(settings: AppSettings, items: list[SigningCheckItem]) -> SigningCheckItem:
    if not settings.signing_enabled:
        return SigningCheckItem(
            name="Signing readiness",
            status="WARN",
            message="Signing is disabled, so no signing will run yet.",
        )

    required_names = {
        "signtool available",
        "certificate path configured",
        "timestamp server configured",
        "Packaged EXE",
        "Installer",
        "Signing script",
    }
    item_map = {item.name: item for item in items}
    missing = [name for name in required_names if item_map.get(name) is None or item_map[name].status != "PASS"]
    if missing:
        return SigningCheckItem(
            name="Signing readiness",
            status="FAIL",
            message="Signing is enabled but prerequisites are incomplete.",
            details=missing,
        )
    return SigningCheckItem(
        name="Signing readiness",
        status="PASS",
        message="Signing prerequisites are ready.",
    )


def _find_signtool() -> Path | None:
    path = shutil.which("signtool.exe")
    if path:
        return Path(path)

    candidates = [
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe"),
        Path(r"C:\Program Files (x86)\Windows Kits\10\bin\x86\signtool.exe"),
        Path(r"C:\Program Files\Windows Kits\10\bin\x64\signtool.exe"),
        Path(r"C:\Program Files\Windows Kits\10\bin\x86\signtool.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _find_installer_path(root: Path) -> Path | None:
    output_dir = root / "installer" / "output"
    if not output_dir.exists():
        return None
    candidates = sorted(output_dir.glob("*.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None
