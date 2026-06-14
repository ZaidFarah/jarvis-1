from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import AppSettings


@dataclass(frozen=True)
class LogFileItem:
    name: str
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class LogListReport:
    logs_dir: Path
    items: list[LogFileItem] = field(default_factory=list)


@dataclass(frozen=True)
class LogTailReport:
    logs_dir: Path
    log_name: str
    path: Path | None
    line_count: int
    lines: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def is_successful(self) -> bool:
        return self.error is None


_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(api[_-]?key)\b\s*[:=]\s*([^\s,;]+)"), r"\1=[redacted]"),
    (re.compile(r"(?i)\b(bearer)\s+([^\s,;]+)"), r"\1 [redacted]"),
    (re.compile(r"(?i)\b(oauth[_-]?token|access[_-]?token|refresh[_-]?token|token)\b\s*[:=]\s*([^\s,;]+)"), r"\1=[redacted]"),
    (re.compile(r"(?i)\b(client[_-]?secret)\b\s*[:=]\s*([^\s,;]+)"), r"\1=[redacted]"),
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "[redacted]"),
)


def list_log_files(settings: AppSettings) -> LogListReport:
    logs_dir = _resolve_logs_dir(settings)
    items: list[LogFileItem] = []
    if logs_dir.exists():
        for path in sorted(logs_dir.rglob("*")):
            if path.is_file():
                items.append(
                    LogFileItem(
                        name=_relative_name(logs_dir, path),
                        path=path.resolve(),
                        size_bytes=path.stat().st_size,
                    )
                )
    return LogListReport(logs_dir=logs_dir, items=items)


def tail_log(settings: AppSettings, log_name: str, *, lines: int = 100) -> LogTailReport:
    logs_dir = _resolve_logs_dir(settings)
    try:
        path = _resolve_log_path(logs_dir, log_name)
    except ValueError as exc:
        return LogTailReport(logs_dir=logs_dir, log_name=log_name, path=None, line_count=max(lines, 0), error=str(exc))

    if not path.exists():
        return LogTailReport(
            logs_dir=logs_dir,
            log_name=log_name,
            path=path,
            line_count=max(lines, 0),
            error=f"Log file not found: {log_name}",
        )

    content = path.read_text(encoding="utf-8", errors="replace")
    raw_lines = content.splitlines()
    tail_count = max(lines, 0)
    selected = raw_lines[-tail_count:] if tail_count else []
    redacted = [_redact_line(line) for line in selected]
    return LogTailReport(
        logs_dir=logs_dir,
        log_name=log_name,
        path=path,
        line_count=tail_count,
        lines=redacted,
    )


def format_logs_list_report(report: LogListReport) -> str:
    lines = [
        "Jarvis Logs List",
        "================",
        f"Logs dir: {report.logs_dir}",
        f"Log files: {len(report.items)}",
    ]
    for item in report.items:
        lines.append(f"- {item.name} ({item.size_bytes} bytes)")
    return "\n".join(lines)


def format_log_tail_report(report: LogTailReport) -> str:
    lines = [
        "Jarvis Log Tail",
        "===============",
        f"Logs dir: {report.logs_dir}",
        f"Log file: {report.log_name}",
        f"Line count: {report.line_count}",
    ]
    if report.error is not None:
        lines.extend(["", f"Error: {report.error}"])
        return "\n".join(lines)
    lines.append("")
    lines.extend(report.lines or ["<empty>"])
    return "\n".join(lines)


def _resolve_logs_dir(settings: AppSettings) -> Path:
    return Path(settings.log_dir).expanduser().resolve()


def _resolve_log_path(logs_dir: Path, log_name: str) -> Path:
    candidate = Path(log_name)
    if candidate.is_absolute():
        raise ValueError("Absolute log paths are not allowed.")
    if not log_name or candidate.anchor:
        raise ValueError("Invalid log name.")

    resolved = (logs_dir / candidate).resolve()
    logs_root = logs_dir.resolve()
    if resolved != logs_root and logs_root not in resolved.parents:
        raise ValueError("Log path escapes the configured logs directory.")
    return resolved


def _relative_name(base_dir: Path, path: Path) -> str:
    return path.relative_to(base_dir).as_posix()


def _redact_line(line: str) -> str:
    redacted = line
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
