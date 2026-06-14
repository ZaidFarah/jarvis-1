from __future__ import annotations

from dataclasses import dataclass

from config.settings import AppSettings
from voice.wake_provider import WakeProviderResolution, resolve_wake_provider


WakeProviderCheckStatus = str


@dataclass(frozen=True)
class WakeProviderCheckReport:
    resolution: WakeProviderResolution
    status: WakeProviderCheckStatus
    message: str

    @property
    def is_successful(self) -> bool:
        return True


def run_wake_provider_check(settings: AppSettings | None = None) -> WakeProviderCheckReport:
    settings = settings or AppSettings(_env_file=None)
    resolution = resolve_wake_provider(settings)

    if resolution.effective_provider == "openwakeword":
        status = "PASS"
        message = "OpenWakeWord is the effective wake provider."
    else:
        status = "WARN"
        if resolution.selected_provider == "openwakeword":
            message = "OpenWakeWord is not effective; Whisper fuzzy fallback is active."
        else:
            message = "Whisper fuzzy wake detection is active."

    return WakeProviderCheckReport(resolution=resolution, status=status, message=message)


def format_wake_provider_check_report(report: WakeProviderCheckReport) -> str:
    resolution = report.resolution
    lines = [
        "Jarvis Wake Provider Check",
        "==========================",
        f"Selected provider: {resolution.selected_provider}",
        f"OpenWakeWord enabled: {_yes_no(resolution.openwakeword_enabled)}",
        f"OpenWakeWord installed: {_yes_no(resolution.openwakeword_installed)}",
        f"Model configured: {_yes_no(resolution.model_configured)}",
        f"Fallback enabled: {_yes_no(resolution.fallback_enabled)}",
        f"Effective provider: {resolution.effective_provider}",
        f"Status: {report.status}",
        f"Message: {report.message}",
    ]
    if resolution.fallback_reason:
        lines.extend(["", f"Fallback reason: {resolution.fallback_reason}"])
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
