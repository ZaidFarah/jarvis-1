from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

from config.settings import AppSettings
from jarvis_runtime.runtime_paths import resolve_runtime_paths
from security.confirmation import ConfirmationResult
from security.permissions import PermissionBroker, PermissionDecision


BACKUP_LOG_SINK_ID: int | None = None
BACKUP_LOG_FILE: Path | None = None
BACKUP_ROOT_NAME = "backups"
BACKUP_CREATE_ACTION = "create backup"
BACKUP_RESTORE_ACTION = "restore backup"
BACKUP_METADATA_NAME = "README.backup.md"


@dataclass(frozen=True)
class BackupItem:
    archive_name: str
    source_path: Path
    restored_path: Path | None = None
    content: str | None = None


@dataclass(frozen=True)
class BackupListItem:
    path: Path
    size_bytes: int
    modified_at: datetime


@dataclass(frozen=True)
class BackupListReport:
    backup_dir: Path
    items: list[BackupListItem] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return True


@dataclass(frozen=True)
class BackupCreateReport:
    backup_dir: Path
    archive_path: Path
    created: bool
    included_items: list[BackupItem] = field(default_factory=list)
    excluded_items: list[BackupItem] = field(default_factory=list)
    metadata_path: Path | None = None
    permission: PermissionDecision | None = None
    confirmation: ConfirmationResult | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.created and not self.errors


@dataclass(frozen=True)
class BackupRestorePlan:
    backup_zip: Path
    restore_items: list[BackupItem] = field(default_factory=list)
    metadata_items: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class BackupRestoreReport:
    backup_zip: Path
    restore_dir: Path
    restored_items: list[BackupItem] = field(default_factory=list)
    permission: PermissionDecision | None = None
    confirmation: ConfirmationResult | None = None
    plan: BackupRestorePlan | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return not self.errors


def get_backup_dir(settings: AppSettings) -> Path:
    runtime_paths = resolve_runtime_paths(settings)
    return runtime_paths.runtime_root / BACKUP_ROOT_NAME


def list_backups(settings: AppSettings) -> BackupListReport:
    backup_dir = get_backup_dir(settings)
    items: list[BackupListItem] = []
    if backup_dir.exists():
        for path in sorted(backup_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            if path.is_file():
                stat = path.stat()
                items.append(
                    BackupListItem(
                        path=path.resolve(),
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
    return BackupListReport(backup_dir=backup_dir, items=items)


def create_backup(
    settings: AppSettings,
    confirmation_handler: Callable[[str, str, str], ConfirmationResult],
    *,
    permission_broker: PermissionBroker | None = None,
) -> BackupCreateReport:
    backup_dir = get_backup_dir(settings)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not settings.backup_enabled:
        return BackupCreateReport(
            backup_dir=backup_dir,
            archive_path=_next_backup_path(backup_dir, settings),
            created=False,
            errors=["Backups are disabled in settings."],
        )
    broker = permission_broker or PermissionBroker(settings)
    permission = broker.check(BACKUP_CREATE_ACTION, description="Create a local backup archive.")
    confirmation = _confirm_if_required(permission, confirmation_handler)
    if not _can_proceed(permission, confirmation):
        return BackupCreateReport(
            backup_dir=backup_dir,
            archive_path=_next_backup_path(backup_dir, settings),
            created=False,
            permission=permission,
            confirmation=confirmation,
            errors=_gate_errors(permission, confirmation),
        )

    plan = _build_backup_plan(settings)
    archive_path = _next_backup_path(backup_dir, settings)
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in plan.included_items:
                if item.content is None:
                    archive.write(item.source_path, item.archive_name)
                else:
                    archive.writestr(item.archive_name, item.content)
            archive.writestr(BACKUP_METADATA_NAME, _build_backup_metadata(settings, plan))
    except Exception as exc:
        safe_error = _format_error(exc)
        _backup_logger(settings).error("Backup creation failed: {}", safe_error)
        return BackupCreateReport(
            backup_dir=backup_dir,
            archive_path=archive_path,
            created=False,
            included_items=plan.included_items,
            excluded_items=plan.excluded_items,
            metadata_path=None,
            permission=permission,
            confirmation=confirmation,
            errors=[safe_error],
        )

    _backup_logger(settings).info(
        "Backup created archive={} included={} excluded={}",
        archive_path,
        len(plan.included_items),
        len(plan.excluded_items),
    )
    return BackupCreateReport(
        backup_dir=backup_dir,
        archive_path=archive_path,
        created=True,
        included_items=plan.included_items,
        excluded_items=plan.excluded_items,
        metadata_path=archive_path,
        permission=permission,
        confirmation=confirmation,
        errors=[],
    )


def plan_restore_backup(settings: AppSettings, backup_zip: Path) -> BackupRestorePlan:
    backup_zip = Path(backup_zip).expanduser().resolve()
    restore_items: list[BackupItem] = []
    metadata_items: list[str] = []
    errors: list[str] = []

    if not backup_zip.exists():
        return BackupRestorePlan(backup_zip=backup_zip, errors=[f"Backup zip not found: {backup_zip}"])

    runtime_paths = resolve_runtime_paths(settings)
    with zipfile.ZipFile(backup_zip, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = _resolve_restore_target(runtime_paths, member.filename)
            if target is None:
                if member.filename == BACKUP_METADATA_NAME:
                    metadata_items.append(member.filename)
                    continue
                errors.append(f"Unsupported or unsafe entry: {member.filename}")
                continue
            restore_items.append(BackupItem(archive_name=member.filename, source_path=backup_zip, restored_path=target))

    return BackupRestorePlan(backup_zip=backup_zip, restore_items=restore_items, metadata_items=metadata_items, errors=errors)


def restore_backup(
    settings: AppSettings,
    backup_zip: Path,
    confirmation_handler: Callable[[str, str, str], ConfirmationResult],
    *,
    permission_broker: PermissionBroker | None = None,
) -> BackupRestoreReport:
    backup_zip = Path(backup_zip).expanduser().resolve()
    if not settings.backup_enabled:
        return BackupRestoreReport(
            backup_zip=backup_zip,
            restore_dir=_restore_root(settings),
            errors=["Backups are disabled in settings."],
        )
    broker = permission_broker or PermissionBroker(settings)
    permission = broker.check(BACKUP_RESTORE_ACTION, description=f"Restore files from {backup_zip.name}.")
    plan = plan_restore_backup(settings, backup_zip)
    print(format_backup_restore_plan(plan), flush=True)
    confirmation = _confirm_if_required(permission, confirmation_handler)
    if not _can_proceed(permission, confirmation) or not plan.is_successful:
        return BackupRestoreReport(
            backup_zip=backup_zip,
            restore_dir=_restore_root(settings),
            permission=permission,
            confirmation=confirmation,
            plan=plan,
            errors=_gate_errors(permission, confirmation) + plan.errors,
        )

    restored: list[BackupItem] = []
    runtime_paths = resolve_runtime_paths(settings)
    try:
        with zipfile.ZipFile(backup_zip, "r") as archive:
            for item in plan.restore_items:
                target = item.restored_path
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item.archive_name) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                restored.append(item)
    except Exception as exc:
        safe_error = _format_error(exc)
        _backup_logger(settings).error("Backup restore failed: {}", safe_error)
        return BackupRestoreReport(
            backup_zip=backup_zip,
            restore_dir=runtime_paths.config_root,
            restored_items=restored,
            permission=permission,
            confirmation=confirmation,
            plan=plan,
            errors=[safe_error],
        )

    _backup_logger(settings).info(
        "Backup restored archive={} restored_items={}",
        backup_zip,
        len(restored),
    )
    return BackupRestoreReport(
        backup_zip=backup_zip,
        restore_dir=runtime_paths.config_root,
        restored_items=restored,
        permission=permission,
        confirmation=confirmation,
        plan=plan,
        errors=[],
    )


def format_backup_list_report(report: BackupListReport) -> str:
    lines = [
        "Jarvis Backup List",
        "==================",
        f"Backup dir: {report.backup_dir}",
        f"Backups: {len(report.items)}",
    ]
    for item in report.items:
        lines.append(f"- {item.path.name} ({item.size_bytes} bytes, {item.modified_at:%Y-%m-%d %H:%M:%S})")
    return "\n".join(lines)


def format_backup_create_report(report: BackupCreateReport) -> str:
    lines = [
        "Jarvis Backup Create",
        "====================",
        f"Backup dir: {report.backup_dir}",
        f"Archive: {report.archive_path}",
        f"Created: {_yes_no(report.created)}",
        f"Included files: {len(report.included_items)}",
        f"Excluded files: {len(report.excluded_items)}",
    ]
    if report.permission is not None:
        lines.extend(
            [
                f"Permission risk: {report.permission.risk_level}",
                f"Permission allowed: {_yes_no(report.permission.allowed)}",
                f"Confirmation required: {_yes_no(report.permission.requires_confirmation)}",
            ]
        )
    if report.confirmation is not None:
        lines.extend(
            [
                f"Confirmation approved: {_yes_no(report.confirmation.approved)}",
                f"Confirmation reason: {report.confirmation.reason}",
            ]
        )
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  {error}" for error in report.errors)
    return "\n".join(lines)


def format_backup_restore_plan(plan: BackupRestorePlan) -> str:
    lines = [
        "Jarvis Backup Restore Plan",
        "==========================",
        f"Backup zip: {plan.backup_zip}",
        f"Restore items: {len(plan.restore_items)}",
    ]
    for item in plan.restore_items:
        lines.append(f"- {item.archive_name} -> {item.restored_path}")
    if plan.metadata_items:
        lines.append("Metadata:")
        lines.extend(f"- {name}" for name in plan.metadata_items)
    if plan.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  {error}" for error in plan.errors)
    return "\n".join(lines)


def format_backup_restore_report(report: BackupRestoreReport) -> str:
    lines = [
        "Jarvis Backup Restore",
        "=====================",
        f"Backup zip: {report.backup_zip}",
        f"Restore dir: {report.restore_dir}",
        f"Restored files: {len(report.restored_items)}",
    ]
    if report.permission is not None:
        lines.extend(
            [
                f"Permission risk: {report.permission.risk_level}",
                f"Permission allowed: {_yes_no(report.permission.allowed)}",
                f"Confirmation required: {_yes_no(report.permission.requires_confirmation)}",
            ]
        )
    if report.confirmation is not None:
        lines.extend(
            [
                f"Confirmation approved: {_yes_no(report.confirmation.approved)}",
                f"Confirmation reason: {report.confirmation.reason}",
            ]
        )
    if report.plan is not None and report.plan.errors:
        lines.extend(["", "Plan errors:"])
        lines.extend(f"  {error}" for error in report.plan.errors)
    if report.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"  {error}" for error in report.errors)
    return "\n".join(lines)


def _build_backup_plan(settings: AppSettings) -> BackupCreateReport:
    runtime_paths = resolve_runtime_paths(settings)
    included: list[BackupItem] = []
    excluded: list[BackupItem] = []

    env_path = runtime_paths.env_path
    if env_path.exists():
        env_text = env_path.read_text(encoding="utf-8")
        if settings.backup_include_env:
            included.append(BackupItem(archive_name="env/.env", source_path=env_path.resolve(), content=env_text))
        else:
            included.append(BackupItem(archive_name="env/.env", source_path=env_path.resolve(), content=_sanitize_env_text(env_text)))

    data_path = runtime_paths.data_path
    if data_path.exists():
        for path in sorted(data_path.rglob("*.db")):
            if path.is_file():
                included.append(BackupItem(archive_name=f"data/{path.relative_to(data_path).as_posix()}", source_path=path.resolve()))

    credentials_path = runtime_paths.credentials_path
    if credentials_path.exists():
        for path in sorted(credentials_path.rglob("token_*.json")):
            if path.is_file() and settings.backup_include_tokens:
                included.append(BackupItem(archive_name=f"credentials/{path.relative_to(credentials_path).as_posix()}", source_path=path.resolve()))
            elif path.is_file():
                excluded.append(BackupItem(archive_name=f"credentials/{path.relative_to(credentials_path).as_posix()}", source_path=path.resolve()))

        secret_path = credentials_path / "google_client_secret.json"
        if secret_path.exists():
            if settings.backup_include_client_secret:
                included.append(BackupItem(archive_name="credentials/google_client_secret.json", source_path=secret_path.resolve()))
            else:
                excluded.append(BackupItem(archive_name="credentials/google_client_secret.json", source_path=secret_path.resolve()))

    return BackupCreateReport(
        backup_dir=get_backup_dir(settings),
        archive_path=_next_backup_path(get_backup_dir(settings), settings),
        created=False,
        included_items=included,
        excluded_items=excluded,
    )


def _build_backup_metadata(settings: AppSettings, report: BackupCreateReport) -> str:
    runtime_paths = resolve_runtime_paths(settings)
    lines = [
        "# Jarvis Backup Metadata",
        "",
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        f"Runtime mode: {runtime_paths.runtime_mode}",
        f"Backup dir: {report.backup_dir}",
        f"Included env: {_yes_no(settings.backup_include_env)}",
        f"Included tokens: {_yes_no(settings.backup_include_tokens)}",
        f"Included client secret: {_yes_no(settings.backup_include_client_secret)}",
        "",
        "Included files:",
    ]
    lines.extend(f"- {item.archive_name}" for item in report.included_items)
    lines.extend(["", "Restore notes:", "- Restore only after confirming the file list."])
    return "\n".join(lines)


def _sanitize_env_text(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, _, value = line.partition("=")
        normalized = key.strip().upper()
        if any(token in normalized for token in {"API_KEY", "TOKEN", "SECRET"}):
            lines.append(f"{key.strip()}=[redacted]")
        else:
            lines.append(f"{key.strip()}={value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _resolve_restore_target(runtime_paths, member_name: str) -> Path | None:
    candidate = Path(member_name)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    if candidate.as_posix() == BACKUP_METADATA_NAME:
        return None
    if candidate.parts[:1] == ("env",) and candidate.name == ".env":
        return _ensure_within(runtime_paths.env_path.parent, runtime_paths.env_path)
    if candidate.parts[:1] == ("data",):
        relative = Path(*candidate.parts[1:])
        return _ensure_within(runtime_paths.data_path, runtime_paths.data_path / relative)
    if candidate.parts[:1] == ("credentials",):
        relative = Path(*candidate.parts[1:])
        return _ensure_within(runtime_paths.credentials_path, runtime_paths.credentials_path / relative)
    return None


def _ensure_within(root: Path, path: Path) -> Path | None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or resolved_root in resolved_path.parents:
        return resolved_path
    return None


def _next_backup_path(backup_dir: Path, settings: AppSettings) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return backup_dir / f"Jarvis-{settings.app_version}-{timestamp}.zip"


def _restore_root(settings: AppSettings) -> Path:
    runtime_paths = resolve_runtime_paths(settings)
    return runtime_paths.config_root


def _confirm_if_required(permission: PermissionDecision, confirmation_handler) -> ConfirmationResult | None:
    if not permission.allowed or not permission.requires_confirmation:
        return None
    return confirmation_handler(permission.action_name, permission.risk_level, permission.description)


def _can_proceed(permission: PermissionDecision, confirmation: ConfirmationResult | None) -> bool:
    if not permission.allowed:
        return False
    if permission.requires_confirmation and (confirmation is None or not confirmation.approved):
        return False
    return True


def _gate_errors(permission: PermissionDecision, confirmation: ConfirmationResult | None) -> list[str]:
    errors: list[str] = []
    errors.extend(permission.errors)
    if confirmation is not None:
        errors.extend(confirmation.errors)
    if permission.requires_confirmation and confirmation is None:
        errors.append("Confirmation was required but not completed.")
    return errors


def _backup_logger(settings: AppSettings):
    global BACKUP_LOG_FILE, BACKUP_LOG_SINK_ID
    log_file = settings.log_dir / "backup.log"
    if BACKUP_LOG_SINK_ID is not None and BACKUP_LOG_FILE == log_file:
        return logger.bind(backup=True)
    if BACKUP_LOG_SINK_ID is not None:
        try:
            logger.remove(BACKUP_LOG_SINK_ID)
        except ValueError:
            pass
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    BACKUP_LOG_SINK_ID = logger.add(
        log_file,
        level="DEBUG",
        rotation="1 MB",
        retention="7 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        filter=lambda record: bool(record["extra"].get("backup")),
    )
    BACKUP_LOG_FILE = log_file
    return logger.bind(backup=True)


def _format_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
