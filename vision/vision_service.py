from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from security.permissions import PermissionBroker
from vision.ocr import OCRExtractionResult, extract_text_from_image
from vision.screenshot import ScreenshotCaptureError, capture_screenshot_image


_VISION_LOG_SINK_ID: int | None = None
_VISION_LOG_FILE: Path | None = None


ScreenshotCapturer = Callable[[], Any]
OCRReader = Callable[[Path], str]
ConfirmationHandler = Callable[[str, str, str], ConfirmationResult]


@dataclass(frozen=True)
class VisionCheckReport:
    enabled: bool
    screenshot_enabled: bool
    ocr_enabled: bool
    screenshot_save_dir: Path
    ocr_provider: str
    screenshot_dependency_available: bool
    ocr_dependency_available: bool
    request_attempted: bool
    success: bool
    text: str
    safe_error: str | None
    log_file: Path
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        if not self.enabled:
            return True
        return self.success


@dataclass(frozen=True)
class ScreenshotResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    screenshot_enabled: bool
    screenshot_path: Path | None = None
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


@dataclass(frozen=True)
class VisionOCRResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    ocr_enabled: bool
    image_path: Path | None = None
    output_truncated: bool = False
    provider_available: bool = False
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


class VisionService:
    """Safe vision foundation with manual screenshot and OCR diagnostics only."""

    def __init__(
        self,
        settings: AppSettings,
        confirmation_handler: ConfirmationHandler | None = None,
        screenshot_capturer: ScreenshotCapturer | None = None,
        ocr_reader: OCRReader | None = None,
    ) -> None:
        self.settings = settings
        self.confirmation_handler = confirmation_handler
        self.screenshot_capturer = screenshot_capturer
        self.ocr_reader = ocr_reader
        self.permission_broker = PermissionBroker(self.settings)
        self.log_file = self.settings.log_dir / "vision.log"
        self.vision_logger = logger.bind(vision=True)
        self._ensure_vision_log_sink()

    def run_check(self) -> VisionCheckReport:
        screenshot_support = self._screenshot_dependency_available()
        ocr_support = self._ocr_dependency_available()

        if not self.settings.vision_enabled:
            text = "Vision is disabled. Enable VISION_ENABLED to capture screenshots or read screen text."
            return self._check_report(
                success=False,
                text=text,
                safe_error=text,
                screenshot_dependency_available=screenshot_support,
                ocr_dependency_available=ocr_support,
                request_attempted=False,
            )

        if not self.settings.screenshot_enabled and not self.settings.ocr_enabled:
            text = "Vision is enabled, but screenshot and OCR are disabled."
            return self._check_report(
                success=False,
                text=text,
                safe_error=text,
                screenshot_dependency_available=screenshot_support,
                ocr_dependency_available=ocr_support,
                request_attempted=False,
            )

        success = (not self.settings.screenshot_enabled or screenshot_support) and (
            not self.settings.ocr_enabled or ocr_support
        )
        text = "Vision diagnostics completed." if success else "Vision dependencies are missing."
        safe_error = None if success else text
        return self._check_report(
            success=success,
            text=text,
            safe_error=safe_error,
            screenshot_dependency_available=screenshot_support,
            ocr_dependency_available=ocr_support,
            request_attempted=False,
        )

    def capture_screenshot(self) -> ScreenshotResult:
        if not self.settings.vision_enabled or not self.settings.screenshot_enabled:
            message = self._screenshot_disabled_message()
            return self._screenshot_result(
                success=False,
                text=message,
                request_attempted=False,
                safe_error=message,
            )

        decision = self.permission_broker.check(
            "take screenshot",
            description="Capture a screenshot of the current screen.",
        )
        if not decision.allowed:
            return self._screenshot_result(
                success=False,
                text=decision.reason,
                request_attempted=False,
                safe_error=decision.reason,
            )

        if self.confirmation_handler is None:
            return self._screenshot_result(
                success=False,
                text="Confirmation is required before capturing screenshots.",
                request_attempted=False,
                safe_error="Confirmation handler is unavailable.",
            )

        confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
        if not confirmation.approved:
            reason = confirmation.reason or "Screenshot capture canceled."
            return self._screenshot_result(success=False, text=reason, request_attempted=False, safe_error=reason)

        try:
            image_path = capture_screenshot_image(self.settings.screenshot_save_dir, capturer=self.screenshot_capturer)
            text = f"Screenshot saved to {image_path}."
            self.vision_logger.info("Screenshot captured path={}", image_path)
            return self._screenshot_result(
                success=True,
                text=text,
                request_attempted=True,
                screenshot_path=image_path,
            )
        except Exception as exc:
            safe_error = format_vision_error(exc)
            self.vision_logger.error("Screenshot capture failed: {}", safe_error)
            return self._screenshot_result(
                success=False,
                text="I couldn't capture a screenshot right now. Please try again later.",
                request_attempted=True,
                safe_error=safe_error,
            )

    def ocr_image(self, image_path: str | Path) -> VisionOCRResult:
        return self._ocr_image_with_gates(Path(image_path))

    def read_screen_text(self) -> VisionOCRResult:
        screenshot_result = self.capture_screenshot()
        if not screenshot_result.success or screenshot_result.screenshot_path is None:
            return self._ocr_result_from_screenshot_failure(screenshot_result)
        return self._ocr_image_with_gates(screenshot_result.screenshot_path, already_confirmed=False)

    def _ocr_image_with_gates(self, image_path: Path, already_confirmed: bool = False) -> VisionOCRResult:
        if not self.settings.vision_enabled or not self.settings.ocr_enabled:
            message = self._ocr_disabled_message()
            return self._ocr_result(
                success=False,
                text=message,
                image_path=image_path,
                request_attempted=False,
                provider_available=False,
                safe_error=message,
            )

        if not image_path.exists() or not image_path.is_file():
            message = "The image file does not exist."
            return self._ocr_result(
                success=False,
                text=message,
                image_path=image_path,
                request_attempted=False,
                provider_available=False,
                safe_error=message,
            )

        if not already_confirmed:
            decision = self.permission_broker.check(
                "read screen text",
                description=f"Run OCR on {image_path.name}.",
            )
            if not decision.allowed:
                return self._ocr_result(
                    success=False,
                    text=decision.reason,
                    image_path=image_path,
                    request_attempted=False,
                    provider_available=False,
                    safe_error=decision.reason,
                )

            if self.confirmation_handler is None:
                return self._ocr_result(
                    success=False,
                    text="Confirmation is required before reading screen text.",
                    image_path=image_path,
                    request_attempted=False,
                    provider_available=False,
                    safe_error="Confirmation handler is unavailable.",
                )

            confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
            if not confirmation.approved:
                reason = confirmation.reason or "OCR canceled."
                return self._ocr_result(
                    success=False,
                    text=reason,
                    image_path=image_path,
                    request_attempted=False,
                    provider_available=False,
                    safe_error=reason,
                )

        try:
            extracted = extract_text_from_image(
                image_path,
                self.settings.ocr_max_output_chars,
                reader=self.ocr_reader,
            )
            if not extracted.success:
                return self._ocr_result(
                    success=False,
                    text=extracted.text,
                    image_path=image_path,
                    request_attempted=True,
                    provider_available=extracted.provider_available,
                    safe_error=extracted.safe_error,
                )
            self.vision_logger.info("OCR completed path={} truncated={}", image_path, extracted.output_truncated)
            return self._ocr_result(
                success=True,
                text=extracted.text,
                image_path=image_path,
                request_attempted=True,
                provider_available=True,
                output_truncated=extracted.output_truncated,
            )
        except Exception as exc:
            safe_error = format_vision_error(exc)
            self.vision_logger.error("OCR failed: {}", safe_error)
            return self._ocr_result(
                success=False,
                text="OCR is unavailable right now.",
                image_path=image_path,
                request_attempted=True,
                provider_available=False,
                safe_error=safe_error,
            )

    def _ocr_result_from_screenshot_failure(self, screenshot_result: ScreenshotResult) -> VisionOCRResult:
        return self._ocr_result(
            success=False,
            text=screenshot_result.text,
            image_path=screenshot_result.screenshot_path,
            request_attempted=screenshot_result.request_attempted,
            provider_available=False,
            safe_error=screenshot_result.safe_error,
        )

    def _check_report(
        self,
        success: bool,
        text: str,
        safe_error: str | None,
        screenshot_dependency_available: bool,
        ocr_dependency_available: bool,
        request_attempted: bool,
    ) -> VisionCheckReport:
        errors = [safe_error] if safe_error else []
        return VisionCheckReport(
            enabled=self.settings.vision_enabled,
            screenshot_enabled=self.settings.screenshot_enabled,
            ocr_enabled=self.settings.ocr_enabled,
            screenshot_save_dir=self.settings.screenshot_save_dir,
            ocr_provider=self.settings.ocr_provider,
            screenshot_dependency_available=screenshot_dependency_available,
            ocr_dependency_available=ocr_dependency_available,
            request_attempted=request_attempted,
            success=success,
            text=text,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _screenshot_result(
        self,
        success: bool,
        text: str,
        request_attempted: bool,
        screenshot_path: Path | None = None,
        safe_error: str | None = None,
    ) -> ScreenshotResult:
        errors = [safe_error] if safe_error else []
        return ScreenshotResult(
            enabled=self.settings.vision_enabled,
            success=success,
            text=text,
            provider="pillow",
            request_attempted=request_attempted,
            screenshot_enabled=self.settings.screenshot_enabled,
            screenshot_path=screenshot_path,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _ocr_result(
        self,
        success: bool,
        text: str,
        image_path: Path | None,
        request_attempted: bool,
        provider_available: bool,
        output_truncated: bool = False,
        safe_error: str | None = None,
    ) -> VisionOCRResult:
        errors = [safe_error] if safe_error else []
        return VisionOCRResult(
            enabled=self.settings.vision_enabled,
            success=success,
            text=text,
            provider=self.settings.ocr_provider,
            request_attempted=request_attempted,
            ocr_enabled=self.settings.ocr_enabled,
            image_path=image_path,
            output_truncated=output_truncated,
            provider_available=provider_available,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _screenshot_disabled_message(self) -> str:
        return "Screenshot capture is disabled. Enable VISION_ENABLED and SCREENSHOT_ENABLED first."

    def _ocr_disabled_message(self) -> str:
        return "OCR is disabled. Enable VISION_ENABLED and OCR_ENABLED first."

    @staticmethod
    def _screenshot_dependency_available() -> bool:
        try:
            from PIL import ImageGrab  # noqa: F401
        except Exception:
            return False
        return True

    @staticmethod
    def _ocr_dependency_available() -> bool:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            return False
        return True

    def _ensure_vision_log_sink(self) -> None:
        global _VISION_LOG_FILE, _VISION_LOG_SINK_ID
        if _VISION_LOG_SINK_ID is not None and _VISION_LOG_FILE == self.log_file:
            return

        if _VISION_LOG_SINK_ID is not None:
            try:
                logger.remove(_VISION_LOG_SINK_ID)
            except ValueError:
                pass

        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        _VISION_LOG_SINK_ID = logger.add(
            self.log_file,
            level="DEBUG",
            rotation="1 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=False,
            diagnose=False,
            filter=lambda record: bool(record["extra"].get("vision")),
        )
        _VISION_LOG_FILE = self.log_file


def format_vision_check_report(report: VisionCheckReport) -> str:
    lines = [
        "Jarvis Vision Check",
        "===================",
        f"Vision enabled: {'yes' if report.enabled else 'no'}",
        f"Screenshot enabled: {'yes' if report.screenshot_enabled else 'no'}",
        f"OCR enabled: {'yes' if report.ocr_enabled else 'no'}",
        f"Screenshot save dir: {report.screenshot_save_dir}",
        f"OCR provider: {report.ocr_provider}",
        f"Screenshot dependency available: {'yes' if report.screenshot_dependency_available else 'no'}",
        f"OCR dependency available: {'yes' if report.ocr_dependency_available else 'no'}",
        f"Request attempted: {'yes' if report.request_attempted else 'no'}",
        f"Request success: {'yes' if report.success else 'no'}",
        f"Diagnostic log: {report.log_file}",
    ]
    if report.text:
        lines.extend(["", "Result:", f"  {report.text}"])
    if report.safe_error:
        lines.extend(["", "Error:", f"  {report.safe_error}"])
    return "\n".join(lines)


def format_screenshot_result(result: ScreenshotResult) -> str:
    lines = [
        "Jarvis Screenshot",
        "=================",
        f"Vision enabled: {'yes' if result.enabled else 'no'}",
        f"Screenshot enabled: {'yes' if result.screenshot_enabled else 'no'}",
        f"Provider: {result.provider}",
        f"Request attempted: {'yes' if result.request_attempted else 'no'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.text:
        lines.extend(["", "Result:", f"  {result.text}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    if result.screenshot_path:
        lines.extend(["", f"Screenshot path: {result.screenshot_path}"])
    return "\n".join(lines)


def format_ocr_result(result: VisionOCRResult) -> str:
    lines = [
        "Jarvis OCR",
        "==========",
        f"Vision enabled: {'yes' if result.enabled else 'no'}",
        f"OCR enabled: {'yes' if result.ocr_enabled else 'no'}",
        f"Provider: {result.provider}",
        f"Request attempted: {'yes' if result.request_attempted else 'no'}",
        f"Provider available: {'yes' if result.provider_available else 'no'}",
        f"Output truncated: {'yes' if result.output_truncated else 'no'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.text:
        lines.extend(["", "Result:", f"  {result.text}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    if result.image_path:
        lines.extend(["", f"Image path: {result.image_path}"])
    return "\n".join(lines)


def format_vision_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"
