from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from config.settings import AppSettings, PROJECT_ROOT


PackageStatus = Literal["PASS", "FAIL"]


EXCLUDED_RELEASE_PATTERNS = [
    ".env",
    "credentials/",
    "tokens",
    "logs/",
    "data/*.db",
    ".git/",
    "build/",
    "releases/*.zip",
    "*.spec",
]


@dataclass(frozen=True)
class ReleasePackageEntry:
    label: str
    source_path: Path
    archive_path: str
    kind: Literal["file", "directory"]


@dataclass(frozen=True)
class ReleasePackagePlan:
    app_name: str
    version: str
    release_name: str
    output_path: Path
    entries: list[ReleasePackageEntry]
    excluded_patterns: list[str]


@dataclass(frozen=True)
class ReleasePackageCheckItem:
    name: str
    status: PackageStatus
    message: str
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReleasePackageCheckReport:
    plan: ReleasePackagePlan
    items: list[ReleasePackageCheckItem]

    @property
    def overall_status(self) -> PackageStatus:
        return "FAIL" if any(item.status == "FAIL" for item in self.items) else "PASS"

    @property
    def is_successful(self) -> bool:
        return self.overall_status == "PASS"


def build_release_package_plan(
    settings: AppSettings | None = None,
    *,
    project_root: Path | None = None,
) -> ReleasePackagePlan:
    settings = settings or AppSettings(_env_file=None)
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    release_name = f"{settings.app_name}-{settings.app_version}-windows"
    output_path = root / "releases" / f"{release_name}.zip"
    internal_path = _resolve_internal_path(root)
    entries = [
        ReleasePackageEntry("Jarvis executable", root / "dist" / "Jarvis" / "Jarvis.exe", "dist/Jarvis/Jarvis.exe", "file"),
        ReleasePackageEntry("PyInstaller internal files", internal_path, "dist/Jarvis/_internal/", "directory"),
        ReleasePackageEntry("README", root / "README.md", "README.md", "file"),
        ReleasePackageEntry("Run launcher", root / "run_jarvis.bat", "run_jarvis.bat", "file"),
        ReleasePackageEntry("Console launcher", root / "run_jarvis_console.bat", "run_jarvis_console.bat", "file"),
        ReleasePackageEntry("Packaged smoke test", root / "test_packaged_app.bat", "test_packaged_app.bat", "file"),
    ]
    return ReleasePackagePlan(
        app_name=settings.app_name,
        version=settings.app_version,
        release_name=release_name,
        output_path=output_path,
        entries=entries,
        excluded_patterns=EXCLUDED_RELEASE_PATTERNS[:],
    )


def run_release_package_check(
    settings: AppSettings | None = None,
    *,
    project_root: Path | None = None,
) -> ReleasePackageCheckReport:
    plan = build_release_package_plan(settings, project_root=project_root)
    items = [
        ReleasePackageCheckItem(
            name="Output ZIP path",
            status="PASS",
            message="Release ZIP output path resolved.",
            details=[str(plan.output_path)],
        ),
        ReleasePackageCheckItem(
            name="Release version",
            status="PASS",
            message=f"Release version is {plan.version}.",
        ),
        _entries_exist_check(plan.entries),
        _excluded_patterns_check(plan.excluded_patterns),
    ]
    return ReleasePackageCheckReport(plan=plan, items=items)


def format_release_package_check_report(report: ReleasePackageCheckReport) -> str:
    lines = [
        "Jarvis Release Package Check",
        "============================",
        f"Version: {report.plan.version}",
        f"Release name: {report.plan.release_name}",
        f"Output ZIP: {report.plan.output_path}",
        "",
        "Included paths:",
    ]
    for entry in report.plan.entries:
        lines.append(f"  {entry.archive_path} <= {entry.source_path}")
    lines.extend(["", "Excluded from release ZIP:"])
    lines.extend(f"  {pattern}" for pattern in report.plan.excluded_patterns)
    lines.append("")
    for item in report.items:
        lines.append(f"{item.status} | {item.name}: {item.message}")
        lines.extend(f"  - {detail}" for detail in item.details)
    lines.extend(["", f"Final package readiness: {report.overall_status}"])
    return "\n".join(lines)


def _resolve_internal_path(root: Path) -> Path:
    pyinstaller_internal = root / "dist" / "Jarvis" / "_internal"
    if pyinstaller_internal.exists():
        return pyinstaller_internal

    legacy_internal = root / "dist" / "Jarvis_internal"
    if legacy_internal.exists():
        return legacy_internal

    return pyinstaller_internal


def _entries_exist_check(entries: list[ReleasePackageEntry]) -> ReleasePackageCheckItem:
    missing: list[str] = []
    for entry in entries:
        exists = entry.source_path.is_dir() if entry.kind == "directory" else entry.source_path.is_file()
        if not exists:
            missing.append(str(entry.source_path))

    if not missing:
        return ReleasePackageCheckItem(
            name="Release inputs",
            status="PASS",
            message="All release package inputs exist.",
        )
    return ReleasePackageCheckItem(
        name="Release inputs",
        status="FAIL",
        message="Required release package inputs are missing.",
        details=missing,
    )


def _excluded_patterns_check(patterns: list[str]) -> ReleasePackageCheckItem:
    required = [".env", "credentials/", "tokens", "logs/", "data/*.db", ".git/"]
    missing = [pattern for pattern in required if pattern not in patterns]
    if not missing:
        return ReleasePackageCheckItem(
            name="Release exclusions",
            status="PASS",
            message="Release plan excludes secrets, logs, data DB files, and .git.",
            details=patterns,
        )
    return ReleasePackageCheckItem(
        name="Release exclusions",
        status="FAIL",
        message="Release plan is missing required exclusions.",
        details=missing,
    )
