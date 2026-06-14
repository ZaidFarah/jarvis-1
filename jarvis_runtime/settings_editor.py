from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from config.settings import AppSettings, PROJECT_ROOT
from jarvis_runtime.config_bootstrap import get_runtime_config_paths


SettingKind = Literal["text", "boolean", "float", "choice"]


@dataclass(frozen=True)
class SafeSettingSpec:
    field_name: str
    env_key: str
    label: str
    kind: SettingKind
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 2


@dataclass(frozen=True)
class SafeSettingsWriteResult:
    env_path: Path
    created_file: bool
    updated_keys: tuple[str, ...]
    preserved_unrelated_keys: bool


SAFE_SETTING_SPECS: tuple[SafeSettingSpec, ...] = (
    SafeSettingSpec("wake_phrase", "WAKE_PHRASE", "Wake phrase", "text"),
    SafeSettingSpec(
        "wake_match_threshold",
        "WAKE_MATCH_THRESHOLD",
        "Wake match threshold",
        "float",
        minimum=0.0,
        maximum=1.0,
        step=0.01,
        decimals=2,
    ),
    SafeSettingSpec("voice_loop_enabled", "VOICE_LOOP_ENABLED", "Voice loop enabled", "boolean"),
    SafeSettingSpec("tts_provider", "TTS_PROVIDER", "TTS provider", "choice", choices=("openai", "pyttsx3")),
    SafeSettingSpec("openai_tts_voice", "OPENAI_TTS_VOICE", "OpenAI TTS voice", "text"),
    SafeSettingSpec("weather_default_city", "WEATHER_DEFAULT_CITY", "Default weather city", "text"),
    SafeSettingSpec("reminders_enabled", "REMINDERS_ENABLED", "Reminders enabled", "boolean"),
    SafeSettingSpec("notifications_enabled", "NOTIFICATIONS_ENABLED", "Notifications enabled", "boolean"),
    SafeSettingSpec("app_launcher_enabled", "APP_LAUNCHER_ENABLED", "App launcher enabled", "boolean"),
    SafeSettingSpec("website_launcher_enabled", "WEBSITE_LAUNCHER_ENABLED", "Website launcher enabled", "boolean"),
    SafeSettingSpec("file_access_enabled", "FILE_ACCESS_ENABLED", "File access enabled", "boolean"),
    SafeSettingSpec("agent_enabled", "AGENT_ENABLED", "Agent enabled", "boolean"),
    SafeSettingSpec("vision_enabled", "VISION_ENABLED", "Vision enabled", "boolean"),
)

SECRET_SETTING_LABELS: tuple[tuple[str, str], ...] = (
    ("openai_api_key", "OpenAI API key"),
    ("weather_api_key", "Weather API key"),
    ("gmail_client_secret_path", "Gmail client secret path"),
    ("gmail_token_path", "Gmail token path"),
    ("calendar_client_secret_path", "Calendar client secret path"),
    ("calendar_token_path", "Calendar token path"),
)


def resolve_settings_env_path(settings: AppSettings) -> Path:
    runtime_paths = get_runtime_config_paths(settings.runtime_mode, PROJECT_ROOT)
    return runtime_paths.env_path


def build_safe_settings_snapshot(settings: AppSettings) -> list[tuple[SafeSettingSpec, str]]:
    snapshot: list[tuple[SafeSettingSpec, str]] = []
    for spec in SAFE_SETTING_SPECS:
        value = getattr(settings, spec.field_name)
        snapshot.append((spec, _format_value(value, spec.kind)))
    return snapshot


def build_redacted_settings_snapshot(settings: AppSettings) -> list[tuple[str, str]]:
    snapshot: list[tuple[str, str]] = []
    for field_name, label in SECRET_SETTING_LABELS:
        if hasattr(settings, field_name):
            snapshot.append((label, "[redacted]"))
    return snapshot


def save_safe_settings(settings: AppSettings, updates: dict[str, Any], *, env_path: Path | None = None) -> SafeSettingsWriteResult:
    target_path = env_path or resolve_settings_env_path(settings)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existed_before = target_path.exists()

    safe_values: dict[str, Any] = {}
    for spec in SAFE_SETTING_SPECS:
        if spec.field_name in updates:
            safe_values[spec.env_key] = updates[spec.field_name]

    original_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    rewritten_text, updated_keys, preserved_unrelated_keys = _rewrite_env_text(original_text, safe_values)
    if not target_path.exists():
        preserved_unrelated_keys = True

    target_path.write_text(rewritten_text, encoding="utf-8")
    return SafeSettingsWriteResult(
        env_path=target_path,
        created_file=not existed_before,
        updated_keys=tuple(updated_keys),
        preserved_unrelated_keys=preserved_unrelated_keys,
    )


def _rewrite_env_text(text: str, updates: dict[str, Any]) -> tuple[str, list[str], bool]:
    if not updates:
        return text, [], True

    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    rewritten: list[str] = []
    updated_keys: list[str] = []
    seen_keys: set[str] = set()
    preserved_unrelated_keys = True

    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rewritten.append(line)
            continue

        key, _, _ = line.partition("=")
        cleaned_key = key.strip()
        if cleaned_key in updates:
            rewritten.append(f"{cleaned_key}={_format_env_value(updates[cleaned_key])}{newline}")
            updated_keys.append(cleaned_key)
            seen_keys.add(cleaned_key)
        else:
            rewritten.append(line)

    missing_keys = [key for key in updates if key not in seen_keys]
    if missing_keys and rewritten and not rewritten[-1].endswith(("\n", "\r")):
        rewritten[-1] = f"{rewritten[-1]}{newline}"
    for key in missing_keys:
        rewritten.append(f"{key}={_format_env_value(updates[key])}{newline}")
        updated_keys.append(key)

    if not rewritten:
        rewritten = [f"{key}={_format_env_value(value)}{newline}" for key, value in updates.items()]

    return "".join(rewritten), updated_keys, preserved_unrelated_keys


def _format_value(value: Any, kind: SettingKind) -> str:
    if kind == "boolean":
        return "yes" if bool(value) else "no"
    if kind == "float":
        return f"{float(value):.2f}"
    return str(value)


def _format_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (int, Path)):
        return str(value)

    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() for ch in text) or any(ch in text for ch in "#;"):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text
