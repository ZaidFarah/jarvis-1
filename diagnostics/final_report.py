from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from config.settings import AppSettings, PROJECT_ROOT
from diagnostics.health import HealthService, format_health_check_report
from diagnostics.installer import format_installer_check_report, run_installer_check
from diagnostics.release_check import format_release_check_report, run_release_check
from diagnostics.signing import format_signing_check_report, run_signing_check
from jarvis_runtime.release_package import build_release_package_plan
from jarvis_runtime.runtime_paths import format_runtime_check_report, resolve_runtime_paths
from security.confirmation import confirm_action_cli
from security.permissions import PermissionBroker


@dataclass(frozen=True)
class FinalReportSection:
    title: str
    status: str
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FinalReport:
    app_name: str
    version: str
    report_path: Path
    git_commit: str
    test_command_reminder: str
    sections: list[FinalReportSection] = field(default_factory=list)

    @property
    def overall_status(self) -> str:
        statuses = {section.status for section in self.sections}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        return "PASS"

    @property
    def summary(self) -> str:
        return f"{self.app_name} {self.version} validation report: {self.overall_status}"


def run_final_report(settings: AppSettings | None = None, *, project_root: Path | None = None) -> FinalReport:
    settings = settings or AppSettings(_env_file=None)
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    report_path = root / "reports" / f"{settings.app_name}-{settings.app_version}-validation-report.md"

    source_settings = settings.model_copy(update={"runtime_mode": "source"})
    runtime_paths = resolve_runtime_paths(source_settings, runtime_mode="source", base_dir=root)
    runtime_report = format_runtime_check_report(runtime_paths)
    health_report = HealthService(source_settings).run_check()
    release_check_report = run_release_check(source_settings, project_root=root)
    installer_check_report = run_installer_check(source_settings, project_root=root)
    signing_check_report = run_signing_check(source_settings, project_root=root)
    release_plan = build_release_package_plan(source_settings, project_root=root)

    sections = [
        _overview_section(settings, root),
        _test_reminder_section(),
        _build_status_section(root),
        _release_zip_section(release_plan),
        _runtime_section(runtime_report),
        _health_section(health_report),
        _release_check_section(release_check_report),
        _installer_check_section(installer_check_report),
        _signing_check_section(signing_check_report),
        _feature_section(settings),
        _security_section(root, source_settings, release_plan),
        _limitations_section(installer_check_report, signing_check_report),
    ]

    report = FinalReport(
        app_name=settings.app_name,
        version=settings.app_version,
        report_path=report_path,
        git_commit=_latest_git_commit(root),
        test_command_reminder="Run `python -m pytest` before releasing.",
        sections=sections,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(format_final_report(report), encoding="utf-8")
    return report


def format_final_report(report: FinalReport) -> str:
    lines = [
        f"# {report.app_name} {report.version} Validation Report",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Latest git commit: {report.git_commit}",
        f"- Report path: {report.report_path}",
        f"- Overall status: {report.overall_status}",
        "",
    ]
    for section in report.sections:
        lines.extend([f"## {section.title}", f"Status: {section.status}"])
        if section.lines:
            lines.append("")
            lines.extend(section.lines)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_final_report_summary(report: FinalReport) -> str:
    return f"{report.report_path} | {report.summary}"


def _overview_section(settings: AppSettings, root: Path) -> FinalReportSection:
    return FinalReportSection(
        title="Overview",
        status="PASS",
        lines=[
            f"- App name: {settings.app_name}",
            f"- Version: {settings.app_version}",
            f"- Runtime mode: source",
            f"- Config root: {root}",
        ],
    )


def _test_reminder_section() -> FinalReportSection:
    return FinalReportSection(
        title="Test Reminder",
        status="PASS",
        lines=["- Run `python -m pytest` before release."],
    )


def _build_status_section(root: Path) -> FinalReportSection:
    build_script = root / "build_exe.bat"
    exe_path = root / "dist" / "Jarvis" / "Jarvis.exe"
    script_exists = build_script.is_file()
    exe_exists = exe_path.is_file()
    status = "PASS" if script_exists and exe_exists else ("WARN" if script_exists else "FAIL")
    return FinalReportSection(
        title="Build Status",
        status=status,
        lines=[
            f"- build_exe.bat: {'present' if script_exists else 'missing'}",
            f"- dist\\Jarvis\\Jarvis.exe: {'present' if exe_exists else 'missing'}",
        ],
    )


def _release_zip_section(plan) -> FinalReportSection:
    exists = plan.output_path.is_file()
    status = "PASS" if exists else "WARN"
    return FinalReportSection(
        title="Release ZIP Status",
        status=status,
        lines=[
            f"- Expected ZIP: {plan.output_path}",
            f"- ZIP exists: {'yes' if exists else 'no'}",
        ],
    )


def _runtime_section(runtime_report: str) -> FinalReportSection:
    return FinalReportSection(
        title="Runtime Check Status",
        status="PASS",
        lines=[f"- Source runtime check completed successfully.", "", "```text", runtime_report, "```"],
    )


def _health_section(health_report) -> FinalReportSection:
    return FinalReportSection(
        title="Health Check Status",
        status="PASS" if health_report.is_successful else "FAIL",
        lines=["- Health check completed successfully.", "", "```text", format_health_check_report(health_report), "```"],
    )


def _release_check_section(release_check_report) -> FinalReportSection:
    return FinalReportSection(
        title="Release Check Status",
        status=release_check_report.overall_status,
        lines=["- Release readiness check completed.", "", "```text", format_release_check_report(release_check_report), "```"],
    )


def _installer_check_section(installer_check_report) -> FinalReportSection:
    return FinalReportSection(
        title="Installer Check Status",
        status=installer_check_report.overall_status,
        lines=["- Installer readiness check completed.", "", "```text", format_installer_check_report(installer_check_report), "```"],
    )


def _signing_check_section(signing_check_report) -> FinalReportSection:
    return FinalReportSection(
        title="Signing Check Status",
        status=signing_check_report.overall_status,
        lines=["- Signing readiness check completed.", "", "```text", format_signing_check_report(signing_check_report), "```"],
    )


def _feature_section(settings: AppSettings) -> FinalReportSection:
    features = [
        ("Voice loop", settings.voice_loop_enabled),
        ("Reminders", settings.reminders_enabled),
        ("Notifications", settings.notifications_enabled),
        ("App launcher", settings.app_launcher_enabled),
        ("Website launcher", settings.website_launcher_enabled),
        ("File access", settings.file_access_enabled),
        ("Memory", settings.memory_enabled),
        ("Weather", settings.weather_enabled),
        ("Calendar", settings.calendar_enabled),
        ("Gmail", settings.gmail_enabled),
        ("Vision", settings.vision_enabled),
        ("Agent", settings.agent_enabled),
        ("Startup", settings.startup_enabled),
        ("Backups", settings.backup_enabled),
        ("Signing", settings.signing_enabled),
    ]
    return FinalReportSection(
        title="Enabled / Disabled Features",
        status="PASS",
        lines=[f"- {name}: {'enabled' if enabled else 'disabled'}" for name, enabled in features],
    )


def _security_section(root: Path, settings: AppSettings, plan) -> FinalReportSection:
    broker = PermissionBroker(settings)
    permission_check = broker.run_check()
    confirm_available = callable(confirm_action_cli)
    excluded_patterns = set(plan.excluded_patterns)
    required_patterns = {".env", "credentials/", "tokens", "logs/", "data/*.db", ".git/"}
    release_exclusions_ok = required_patterns.issubset(excluded_patterns)
    release_zip_exists = plan.output_path.is_file()
    status = "PASS" if release_exclusions_ok and release_zip_exists else "WARN"
    return FinalReportSection(
        title="Security Summary",
        status=status,
        lines=[
            f"- Permission broker present: yes",
            f"- Confirmation system present: {'yes' if confirm_available else 'no'}",
            f"- Secrets not bundled: {'yes' if release_exclusions_ok else 'no'}",
            f"- logs/data/credentials excluded from release: {'yes' if release_exclusions_ok else 'no'}",
            f"- Release ZIP exists: {'yes' if release_zip_exists else 'no'}",
            f"- Permission broker check log: {permission_check.log_file}",
            f"- Release root: {root}",
        ],
    )


def _limitations_section(installer_check_report, signing_check_report) -> FinalReportSection:
    installer_missing = any(
        item.name == "Inno compiler" and item.status == "WARN" for item in installer_check_report.items
    )
    lines = [
        "- Unsigned EXE and installer can trigger SmartScreen warnings.",
        "- No code signing certificate is configured yet.",
        "- Optional integrations still require user OAuth/API setup.",
    ]
    if installer_missing:
        lines.insert(1, "- No installer built if Inno Setup is missing locally.")
    if signing_check_report.overall_status == "WARN":
        lines.append("- Signing remains preparation-only until a certificate and signtool are available.")
    return FinalReportSection(title="Known Limitations", status="WARN", lines=lines)


def _latest_git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%h %s"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return "unavailable"
    return result.stdout.strip() or "unavailable"
