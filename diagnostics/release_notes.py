from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import AppSettings, PROJECT_ROOT


@dataclass(frozen=True)
class ReleaseNotesReport:
    version: str
    notes_path: Path
    text: str

    @property
    def is_successful(self) -> bool:
        return self.notes_path.is_file()


def run_release_notes(settings: AppSettings | None = None, *, project_root: Path | None = None) -> ReleaseNotesReport:
    settings = settings or AppSettings(_env_file=None)
    root = (project_root or PROJECT_ROOT).expanduser().resolve()
    notes_path = root / "releases" / f"RELEASE_NOTES_{settings.app_version}.md"
    text = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else ""
    return ReleaseNotesReport(version=settings.app_version, notes_path=notes_path, text=text)


def format_release_notes_report(report: ReleaseNotesReport) -> str:
    if not report.notes_path.is_file():
        return "\n".join(
            [
                "Jarvis Release Notes",
                "====================",
                f"Version: {report.version}",
                f"Notes path: {report.notes_path}",
                "Release notes file is missing.",
            ]
        )

    return "\n".join(
        [
            "Jarvis Release Notes",
            "====================",
            f"Version: {report.version}",
            f"Notes path: {report.notes_path}",
            "",
            report.text.rstrip(),
        ]
    )
