from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import AppSettings, PROJECT_ROOT


@dataclass(frozen=True)
class InstallerCheckItem:
    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstallerCheckReport:
    installer_script: Path
    output_dir: Path
    items: list[InstallerCheckItem] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return all(item.status != "FAIL" for item in self.items)

    @property
    def overall_status(self) -> str:
        statuses = {item.status for item in self.items}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"


def run_installer_check(settings: AppSettings, *, project_root: Path | None = None) -> InstallerCheckReport:
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    script = root / "installer" / "JarvisInstaller.iss"
    output_dir = root / "installer" / "output"
    exe_path = root / "dist" / "Jarvis" / "Jarvis.exe"
    script_text = script.read_text(encoding="utf-8") if script.exists() else ""
    items = [
        _check_file("Packaged EXE", exe_path, "dist\\Jarvis\\Jarvis.exe exists.", "dist\\Jarvis\\Jarvis.exe is missing."),
        _check_file("Inno script", script, "Installer script exists.", "Installer script is missing."),
        _forbidden_file_source_check("Forbidden files excluded", script_text, [".env", "credentials", "token", "logs", "data", "build", "releases", ".git"]),
        _output_dir_check(output_dir),
        _compiler_check(),
        _no_secret_reference_check(script_text),
        _no_hklm_service_check(script_text),
    ]
    return InstallerCheckReport(installer_script=script, output_dir=output_dir, items=items)


def format_installer_check_report(report: InstallerCheckReport) -> str:
    lines = [
        "Jarvis Installer Check",
        "======================",
        f"Installer script: {report.installer_script}",
        f"Output dir: {report.output_dir}",
    ]
    for item in report.items:
        lines.append(f"{item.status} | {item.name}: {item.message}")
        lines.extend(f"  - {detail}" for detail in item.details)
    lines.append("")
    status = report.overall_status
    lines.append(f"Final installer readiness: {status}")
    return "\n".join(lines)


def _check_file(name: str, path: Path, pass_message: str, fail_message: str) -> InstallerCheckItem:
    if path.is_file():
        return InstallerCheckItem(name=name, status="PASS", message=pass_message, details=[str(path)])
    return InstallerCheckItem(name=name, status="FAIL", message=fail_message, details=[str(path)])


def _output_dir_check(output_dir: Path) -> InstallerCheckItem:
    return InstallerCheckItem(
        name="Output folder",
        status="PASS",
        message="Installer output goes to installer\\output.",
        details=[str(output_dir)],
    )


def _compiler_check() -> InstallerCheckItem:
    compiler = shutil.which("ISCC.exe")
    if compiler:
        return InstallerCheckItem(name="Inno compiler", status="PASS", message="Inno Setup compiler available.", details=[compiler])

    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return InstallerCheckItem(name="Inno compiler", status="PASS", message="Inno Setup compiler available.", details=[str(candidate)])
    return InstallerCheckItem(name="Inno compiler", status="WARN", message="Inno Setup compiler not found locally.", details=[])


def _forbidden_file_source_check(name: str, text: str, forbidden_tokens: list[str]) -> InstallerCheckItem:
    source_lines = [line for line in text.splitlines() if line.strip().lower().startswith("source:")]
    found = [token for token in forbidden_tokens if any(token.lower() in line.lower() for line in source_lines)]
    if found:
        return InstallerCheckItem(name=name, status="FAIL", message="Installer script references forbidden content.", details=found)
    return InstallerCheckItem(name=name, status="PASS", message="Installer script does not reference forbidden content.")


def _no_secret_reference_check(text: str) -> InstallerCheckItem:
    secret_tokens = ["openai_api_key", "client_secret", "token_gmail", "token_calendar", "credentials/token_", ".env"]
    found = [token for token in secret_tokens if token.lower() in text.lower()]
    if found:
        return InstallerCheckItem(name="Secret references", status="FAIL", message="Installer script references secrets.", details=found)
    return InstallerCheckItem(name="Secret references", status="PASS", message="Installer script does not reference secrets.")


def _no_hklm_service_check(text: str) -> InstallerCheckItem:
    lowered = text.lower()
    found = [token for token in ("hklm", "service", "windows service") if token in lowered]
    if found:
        return InstallerCheckItem(name="HKLM/services", status="FAIL", message="Installer script references HKLM or services.", details=found)
    return InstallerCheckItem(name="HKLM/services", status="PASS", message="Installer script does not reference HKLM or services.")
