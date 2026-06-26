from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from security.permissions import PermissionBroker
from services.openai_service import OpenAIService, OpenAIVisionResult
from vision.ocr import extract_text_from_image
from vision.screenshot import (
    MonitorInfo,
    ScreenshotCaptureError,
    capture_screenshot_details,
    list_monitors,
)


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
    openai_vision_enabled: bool
    openai_api_key_detected: bool
    screenshot_save_dir: Path
    ocr_provider: str
    openai_vision_model: str
    openai_vision_max_image_bytes: int
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
    monitor_index: int | None = None
    monitor_label: str | None = None
    all_monitors: bool = False
    image_size: tuple[int, int] | None = None
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
    screenshot_path: Path | None = None
    monitor_index: int | None = None
    monitor_label: str | None = None
    image_size: tuple[int, int] | None = None
    tesseract_path: str | None = None
    output_truncated: bool = False
    provider_available: bool = False
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


@dataclass(frozen=True)
class VisionAnalysisResult:
    enabled: bool
    success: bool
    text: str
    provider: str
    request_attempted: bool
    openai_vision_enabled: bool
    image_path: Path | None = None
    screenshot_path: Path | None = None
    monitor_index: int | None = None
    monitor_label: str | None = None
    image_size: tuple[int, int] | None = None
    provider_available: bool = False
    safe_error: str | None = None
    log_file: Path | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        return self.success


class VisionService:
    """Safe vision foundation for screenshots, OCR, and OpenAI vision."""

    def __init__(
        self,
        settings: AppSettings,
        confirmation_handler: ConfirmationHandler | None = None,
        screenshot_capturer: ScreenshotCapturer | None = None,
        ocr_reader: OCRReader | None = None,
        openai_service: OpenAIService | None = None,
        allowed_image_roots: set[Path] | None = None,
    ) -> None:
        self.settings = settings
        self.confirmation_handler = confirmation_handler
        self.screenshot_capturer = screenshot_capturer
        self.ocr_reader = ocr_reader
        self.openai_service = openai_service or OpenAIService(self.settings)
        self.permission_broker = PermissionBroker(self.settings)
        self.allowed_image_roots = {Path(root).expanduser().resolve() for root in (allowed_image_roots or set())}
        self.log_file = self.settings.log_dir / "vision.log"
        self.vision_logger = logger.bind(vision=True)
        self._ensure_vision_log_sink()

    def run_check(self) -> VisionCheckReport:
        screenshot_support = self._screenshot_dependency_available()
        ocr_support = self._ocr_dependency_available()
        screen_vision_ready = self._screen_vision_enabled()

        if not screen_vision_ready:
            text = "Vision is disabled. Enable SCREEN_VISION_ENABLED to capture screenshots or read screen text."
            return self._check_report(
                success=False,
                text=text,
                safe_error=text,
                screenshot_dependency_available=screenshot_support,
                ocr_dependency_available=ocr_support,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                openai_api_key_detected=self.settings.has_openai_api_key,
                request_attempted=False,
            )

        openai_vision_support = self.settings.openai_vision_enabled and self.settings.has_openai_api_key

        if not self._screenshot_ready() and not self.settings.ocr_enabled:
            if not openai_vision_support:
                text = "Vision is enabled, but screenshot, OCR, and OpenAI vision are disabled."
            else:
                text = "Vision is enabled, but screenshot and OCR are disabled."
            return self._check_report(
                success=False,
                text=text,
                safe_error=text,
                screenshot_dependency_available=screenshot_support,
                ocr_dependency_available=ocr_support,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                openai_api_key_detected=self.settings.has_openai_api_key,
                request_attempted=False,
            )

        openai_key_ready = not self.settings.openai_vision_enabled or self.settings.has_openai_api_key
        success = (
            (self._screenshot_ready() and screenshot_support)
            and (not self.settings.ocr_enabled or ocr_support)
            and openai_key_ready
        )
        if success:
            text = "Vision diagnostics completed."
            safe_error = None
        elif self.settings.openai_vision_enabled and not self.settings.has_openai_api_key:
            text = "OpenAI vision is enabled, but OPENAI_API_KEY is not set."
            safe_error = text
        else:
            text = "Vision dependencies are missing."
            safe_error = text
        return self._check_report(
            success=success,
            text=text,
            safe_error=safe_error,
            screenshot_dependency_available=screenshot_support,
            ocr_dependency_available=ocr_support,
            openai_vision_enabled=self.settings.openai_vision_enabled,
            openai_api_key_detected=self.settings.has_openai_api_key,
            request_attempted=False,
        )

    def capture_screenshot(self, monitor: str | int | None = None, all_monitors: bool | None = None) -> ScreenshotResult:
        if not self._screen_vision_enabled() or not self._screenshot_ready():
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
            capture_all = self.settings.screen_capture_all_monitors if all_monitors is None else all_monitors
            target_monitor = self.settings.screen_capture_monitor if monitor is None else monitor
            details = capture_screenshot_details(
                self.settings.screenshot_save_dir,
                capturer=self.screenshot_capturer,
                monitor=target_monitor,
                all_monitors=capture_all,
            )
            image_path = details.image_path
            text = f"Screenshot saved to {image_path}."
            self.vision_logger.info(
                "Screenshot captured path={} monitor={} all_monitors={} size={}",
                image_path,
                details.monitor.label if details.monitor else "all monitors",
                details.all_monitors,
                details.image_size,
            )
            return self._screenshot_result(
                success=True,
                text=text,
                request_attempted=True,
                screenshot_path=image_path,
                monitor_index=details.monitor.index if details.monitor else None,
                monitor_label=details.monitor.label if details.monitor else ("All monitors" if details.all_monitors else None),
                all_monitors=details.all_monitors,
                image_size=details.image_size,
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

    def list_screens(self) -> list[MonitorInfo]:
        return list_monitors()

    def ocr_image(self, image_path: str | Path) -> VisionOCRResult:
        return self._ocr_image_with_gates(Path(image_path))

    def read_screen_text(self, monitor: str | int | None = None, all_monitors: bool | None = None) -> VisionOCRResult:
        screenshot_result = self.capture_screenshot(monitor=monitor, all_monitors=all_monitors)
        if not screenshot_result.success or screenshot_result.screenshot_path is None:
            return self._ocr_result_from_screenshot_failure(screenshot_result)
        if self.settings.ocr_enabled:
            try:
                extracted = extract_text_from_image(
                    screenshot_result.screenshot_path,
                    self.settings.ocr_max_output_chars,
                    reader=self.ocr_reader,
                )
                if extracted.success:
                    cleaned = extracted.text.strip()
                    if cleaned:
                        self.vision_logger.info(
                            "Screen OCR completed path={} truncated={} tesseract_path={}",
                            screenshot_result.screenshot_path,
                            extracted.output_truncated,
                            extracted.tesseract_path,
                        )
                        return self._ocr_result(
                            success=True,
                            text=cleaned,
                            image_path=screenshot_result.screenshot_path,
                            screenshot_path=screenshot_result.screenshot_path,
                            monitor_index=screenshot_result.monitor_index,
                            monitor_label=screenshot_result.monitor_label,
                            image_size=extracted.image_size,
                            tesseract_path=extracted.tesseract_path,
                            request_attempted=True,
                            provider_available=True,
                            output_truncated=extracted.output_truncated,
                        )
                else:
                    self.vision_logger.warning(
                        "Screen OCR failed path={} error={}",
                        screenshot_result.screenshot_path,
                        extracted.safe_error,
                    )
                    if extracted.safe_error is not None:
                        fallback_text = self._openai_extract_screen_text(
                            screenshot_result.screenshot_path,
                            screenshot_result,
                        )
                        if fallback_text is not None:
                            return self._ocr_result(
                                success=True,
                                text=fallback_text,
                                image_path=screenshot_result.screenshot_path,
                                screenshot_path=screenshot_result.screenshot_path,
                                monitor_index=screenshot_result.monitor_index,
                                monitor_label=screenshot_result.monitor_label,
                                image_size=extracted.image_size,
                                tesseract_path=extracted.tesseract_path,
                                request_attempted=True,
                                provider_available=True,
                                safe_error=extracted.safe_error,
                            )
            except Exception as exc:
                safe_error = format_vision_error(exc)
                self.vision_logger.error("Screen OCR fallback failed: {}", safe_error)
                openai_text = self._openai_extract_screen_text(screenshot_result.screenshot_path, screenshot_result)
                if openai_text is not None:
                    return self._ocr_result(
                        success=True,
                        text=openai_text,
                        image_path=screenshot_result.screenshot_path,
                        screenshot_path=screenshot_result.screenshot_path,
                        monitor_index=screenshot_result.monitor_index,
                        monitor_label=screenshot_result.monitor_label,
                        request_attempted=True,
                        provider_available=True,
                        image_size=screenshot_result.image_size,
                        safe_error=safe_error,
                    )
                return self._ocr_result(
                    success=True,
                    text=screenshot_result.text,
                    image_path=screenshot_result.screenshot_path,
                    screenshot_path=screenshot_result.screenshot_path,
                    monitor_index=screenshot_result.monitor_index,
                    monitor_label=screenshot_result.monitor_label,
                    request_attempted=True,
                    provider_available=False,
                    image_size=screenshot_result.image_size,
                    safe_error=safe_error,
                )

        openai_text = self._openai_extract_screen_text(screenshot_result.screenshot_path, screenshot_result)
        if openai_text is not None:
            return self._ocr_result(
                success=True,
                text=openai_text,
                image_path=screenshot_result.screenshot_path,
                screenshot_path=screenshot_result.screenshot_path,
                monitor_index=screenshot_result.monitor_index,
                monitor_label=screenshot_result.monitor_label,
                request_attempted=True,
                provider_available=True,
                image_size=screenshot_result.image_size,
            )
        return self._ocr_result(
            success=True,
            text=screenshot_result.text,
            image_path=screenshot_result.screenshot_path,
            screenshot_path=screenshot_result.screenshot_path,
            monitor_index=screenshot_result.monitor_index,
            monitor_label=screenshot_result.monitor_label,
            request_attempted=True,
            provider_available=False,
            image_size=screenshot_result.image_size,
        )

    def analyze_image(self, image_path: str | Path) -> VisionAnalysisResult:
        return self._analyze_image_with_gates(Path(image_path))

    def analyze_screenshot(self, monitor: str | int | None = None, all_monitors: bool | None = None) -> VisionAnalysisResult:
        screenshot_result = self.capture_screenshot(monitor=monitor, all_monitors=all_monitors)
        if not screenshot_result.success or screenshot_result.screenshot_path is None:
            return self._analysis_result_from_screenshot_failure(screenshot_result)
        return self._analyze_image_with_gates(screenshot_result.screenshot_path, already_confirmed=False)

    def analyze_screen(self, monitor: str | int | None = None, all_monitors: bool | None = None) -> VisionAnalysisResult:
        screenshot_result = self.capture_screenshot(monitor=monitor, all_monitors=all_monitors)
        if not screenshot_result.success or screenshot_result.screenshot_path is None:
            return self._analysis_result_from_screenshot_failure(screenshot_result)

        ocr_text = self._read_screen_text_from_image(screenshot_result.screenshot_path)
        if self.settings.openai_vision_enabled and self.settings.has_openai_api_key:
            result = self._analyze_captured_screenshot(screenshot_result.screenshot_path)
            if result.success:
                text = self._combine_screen_summary(result.text, ocr_text)
                return self._analysis_result(
                    success=True,
                    text=text,
                    image_path=screenshot_result.screenshot_path,
                    screenshot_path=screenshot_result.screenshot_path,
                    monitor_index=screenshot_result.monitor_index,
                    monitor_label=screenshot_result.monitor_label,
                    image_size=screenshot_result.image_size,
                    request_attempted=True,
                    provider_available=True,
                    openai_vision_enabled=self.settings.openai_vision_enabled,
                )
            fallback_text = self._screen_fallback_text(screenshot_result.screenshot_path, ocr_text, result.safe_error)
            return self._analysis_result(
                success=True,
                text=fallback_text,
                image_path=screenshot_result.screenshot_path,
                screenshot_path=screenshot_result.screenshot_path,
                monitor_index=screenshot_result.monitor_index,
                monitor_label=screenshot_result.monitor_label,
                image_size=screenshot_result.image_size,
                request_attempted=True,
                provider_available=bool(ocr_text),
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=result.safe_error,
            )

        fallback_text = self._screen_fallback_text(screenshot_result.screenshot_path, ocr_text, None)
        return self._analysis_result(
            success=True,
            text=fallback_text,
            image_path=screenshot_result.screenshot_path,
            screenshot_path=screenshot_result.screenshot_path,
            monitor_index=screenshot_result.monitor_index,
            monitor_label=screenshot_result.monitor_label,
            image_size=screenshot_result.image_size,
            request_attempted=True,
            provider_available=bool(ocr_text),
            openai_vision_enabled=self.settings.openai_vision_enabled,
        )

    def list_screens_text(self) -> str:
        screens = self.list_screens()
        if not screens:
            return "I couldn't detect any screens."
        lines = ["Detected screens:"]
        for screen in screens:
            lines.append(
                f"{screen.index}. {screen.label} - {screen.width}x{screen.height} at ({screen.left}, {screen.top})"
            )
        return "\n".join(lines)

    def _ocr_image_with_gates(self, image_path: Path, already_confirmed: bool = False) -> VisionOCRResult:
        if not self._screen_vision_enabled() or not self.settings.ocr_enabled:
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
            screenshot_path=screenshot_result.screenshot_path,
            monitor_index=screenshot_result.monitor_index,
            monitor_label=screenshot_result.monitor_label,
            image_size=screenshot_result.image_size,
            safe_error=screenshot_result.safe_error,
        )

    def _analysis_result_from_screenshot_failure(self, screenshot_result: ScreenshotResult) -> VisionAnalysisResult:
        return self._analysis_result(
            success=False,
            text=screenshot_result.text,
            image_path=screenshot_result.screenshot_path,
            request_attempted=screenshot_result.request_attempted,
            provider_available=False,
            openai_vision_enabled=self.settings.openai_vision_enabled,
            screenshot_path=screenshot_result.screenshot_path,
            monitor_index=screenshot_result.monitor_index,
            monitor_label=screenshot_result.monitor_label,
            image_size=screenshot_result.image_size,
            safe_error=screenshot_result.safe_error,
        )

    def _analyze_captured_screenshot(self, image_path: Path) -> VisionAnalysisResult:
        return self._analyze_image_with_gates(image_path, already_confirmed=False)

    def _openai_extract_screen_text(self, image_path: Path, screenshot_result: ScreenshotResult) -> str | None:
        if not self.settings.openai_vision_enabled or not self.settings.has_openai_api_key:
            return None
        try:
            result = self.openai_service.analyze_image(
                image_path,
                prompt="Extract the visible text from this screen as faithfully as possible. Preserve line breaks when helpful.",
                system_prompt=self.settings.system_prompt,
            )
        except Exception as exc:
            safe_error = format_vision_error(exc)
            self.vision_logger.error("OpenAI vision text extraction failed: {}", safe_error)
            return None
        if not result.success or not result.text.strip():
            return None
        lines = [result.text.strip(), f"Screenshot saved to {image_path}."]
        if screenshot_result.monitor_label:
            lines.append(f"Captured from {screenshot_result.monitor_label}.")
        return "\n\n".join(lines)

    def _read_screen_text_from_image(self, image_path: Path) -> str:
        if not self.settings.ocr_enabled:
            return ""

        try:
            extracted = extract_text_from_image(
                image_path,
                self.settings.ocr_max_output_chars,
                reader=self.ocr_reader,
            )
        except Exception:
            return ""

        if not extracted.success:
            return ""
        return extracted.text.strip()

    @staticmethod
    def _combine_screen_summary(summary: str, ocr_text: str) -> str:
        summary_text = summary.strip()
        ocr_clean = ocr_text.strip()
        if not ocr_clean:
            return summary_text
        if ocr_clean.lower() in summary_text.lower():
            return summary_text
        return f"{summary_text}\n\nOCR text:\n{ocr_clean}"

    @staticmethod
    def _screen_fallback_text(image_path: Path, ocr_text: str, error: str | None) -> str:
        if ocr_text.strip():
            return f"{ocr_text.strip()}\n\nScreenshot saved to {image_path}."
        if error:
            return f"OpenAI vision was unavailable, so I saved a screenshot to {image_path}."
        return f"Screenshot saved to {image_path}."

    def _analyze_image_with_gates(self, image_path: Path, already_confirmed: bool = False) -> VisionAnalysisResult:
        if not self._screen_vision_enabled() or not self.settings.openai_vision_enabled:
            message = self._analysis_disabled_message()
            return self._analysis_result(
                success=False,
                text=message,
                image_path=image_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=message,
            )

        normalized_path, path_error = self._validate_analysis_path(image_path)
        if path_error is not None or normalized_path is None:
            message = path_error or "The image file cannot be analyzed."
            return self._analysis_result(
                success=False,
                text=message,
                image_path=image_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=message,
            )

        if not self._is_supported_image(normalized_path):
            message = "Only image files can be analyzed."
            return self._analysis_result(
                success=False,
                text=message,
                image_path=normalized_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=message,
            )

        if normalized_path.stat().st_size > self.settings.openai_vision_max_image_bytes:
            message = "The image is too large to analyze safely."
            return self._analysis_result(
                success=False,
                text=message,
                image_path=normalized_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=message,
            )

        safety_error = self._screen_image_for_sensitive_content(normalized_path)
        if safety_error is not None:
            return self._analysis_result(
                success=False,
                text=safety_error,
                image_path=normalized_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=safety_error,
            )

        decision = self.permission_broker.check(
            "send image to openai",
            description=f"Analyze image {normalized_path.name} with OpenAI vision.",
        )
        if not decision.allowed:
            return self._analysis_result(
                success=False,
                text=decision.reason,
                image_path=normalized_path,
                request_attempted=False,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=decision.reason,
            )

        if not already_confirmed:
            if self.confirmation_handler is None:
                return self._analysis_result(
                    success=False,
                    text="Confirmation is required before sending images to OpenAI.",
                    image_path=normalized_path,
                    request_attempted=False,
                    provider_available=False,
                    openai_vision_enabled=self.settings.openai_vision_enabled,
                    safe_error="Confirmation handler is unavailable.",
                )

            confirmation = self.confirmation_handler(decision.action_name, decision.risk_level, decision.description)
            if not confirmation.approved:
                reason = confirmation.reason or "Image analysis canceled."
                return self._analysis_result(
                    success=False,
                    text=reason,
                    image_path=normalized_path,
                    request_attempted=False,
                    provider_available=False,
                    openai_vision_enabled=self.settings.openai_vision_enabled,
                    safe_error=reason,
                )

        try:
            result = self.openai_service.analyze_image(
                normalized_path,
                prompt="Describe the visible screen or image content clearly and concisely.",
                system_prompt=self.settings.system_prompt,
            )
            if not result.success:
                return self._analysis_result(
                    success=False,
                    text=result.text,
                    image_path=normalized_path,
                    request_attempted=result.request_attempted,
                    provider_available=result.provider_available,
                    openai_vision_enabled=self.settings.openai_vision_enabled,
                    safe_error=result.safe_error,
                )
            self.vision_logger.info("OpenAI vision analysis completed path={}", normalized_path)
            return self._analysis_result(
                success=True,
                text=result.text,
                image_path=normalized_path,
                request_attempted=True,
                provider_available=True,
                openai_vision_enabled=self.settings.openai_vision_enabled,
            )
        except Exception as exc:
            safe_error = format_vision_error(exc)
            self.vision_logger.error("OpenAI vision analysis failed: {}", safe_error)
            return self._analysis_result(
                success=False,
                text="OpenAI vision is unavailable right now.",
                image_path=normalized_path,
                request_attempted=True,
                provider_available=False,
                openai_vision_enabled=self.settings.openai_vision_enabled,
                safe_error=safe_error,
            )

    def _check_report(
        self,
        success: bool,
        text: str,
        safe_error: str | None,
        screenshot_dependency_available: bool,
        ocr_dependency_available: bool,
        openai_vision_enabled: bool,
        openai_api_key_detected: bool,
        request_attempted: bool,
    ) -> VisionCheckReport:
        errors = [safe_error] if safe_error else []
        return VisionCheckReport(
            enabled=self._screen_vision_enabled(),
            screenshot_enabled=self.settings.screenshot_enabled,
            ocr_enabled=self.settings.ocr_enabled,
            openai_vision_enabled=openai_vision_enabled,
            openai_api_key_detected=openai_api_key_detected,
            screenshot_save_dir=self.settings.screenshot_save_dir,
            ocr_provider=self.settings.ocr_provider,
            openai_vision_model=self.settings.openai_vision_model,
            openai_vision_max_image_bytes=self.settings.openai_vision_max_image_bytes,
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
        monitor_index: int | None = None,
        monitor_label: str | None = None,
        all_monitors: bool = False,
        image_size: tuple[int, int] | None = None,
        safe_error: str | None = None,
    ) -> ScreenshotResult:
        errors = [safe_error] if safe_error else []
        return ScreenshotResult(
            enabled=self._screen_vision_enabled(),
            success=success,
            text=text,
            provider="pillow",
            request_attempted=request_attempted,
            screenshot_enabled=self._screenshot_ready(),
            screenshot_path=screenshot_path,
            monitor_index=monitor_index,
            monitor_label=monitor_label,
            all_monitors=all_monitors,
            image_size=image_size,
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
        screenshot_path: Path | None = None,
        monitor_index: int | None = None,
        monitor_label: str | None = None,
        image_size: tuple[int, int] | None = None,
        tesseract_path: str | None = None,
        safe_error: str | None = None,
    ) -> VisionOCRResult:
        errors = [safe_error] if safe_error else []
        return VisionOCRResult(
            enabled=self._screen_vision_enabled(),
            success=success,
            text=text,
            provider=self.settings.ocr_provider,
            request_attempted=request_attempted,
            ocr_enabled=self.settings.ocr_enabled,
            image_path=image_path,
            screenshot_path=screenshot_path,
            monitor_index=monitor_index,
            monitor_label=monitor_label,
            image_size=image_size,
            tesseract_path=tesseract_path,
            output_truncated=output_truncated,
            provider_available=provider_available,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _analysis_result(
        self,
        success: bool,
        text: str,
        image_path: Path | None,
        request_attempted: bool,
        provider_available: bool,
        openai_vision_enabled: bool,
        screenshot_path: Path | None = None,
        monitor_index: int | None = None,
        monitor_label: str | None = None,
        image_size: tuple[int, int] | None = None,
        safe_error: str | None = None,
    ) -> VisionAnalysisResult:
        errors = [safe_error] if safe_error else []
        return VisionAnalysisResult(
            enabled=self._screen_vision_enabled(),
            success=success,
            text=text,
            provider=self.settings.openai_vision_model,
            request_attempted=request_attempted,
            openai_vision_enabled=openai_vision_enabled,
            image_path=image_path,
            screenshot_path=screenshot_path,
            monitor_index=monitor_index,
            monitor_label=monitor_label,
            image_size=image_size,
            provider_available=provider_available,
            safe_error=safe_error,
            log_file=self.log_file,
            errors=errors,
        )

    def _screenshot_disabled_message(self) -> str:
        return "Screenshot capture is disabled. Enable SCREEN_VISION_ENABLED and SCREENSHOT_ENABLED first."

    def _ocr_disabled_message(self) -> str:
        return "OCR is disabled. Enable SCREEN_VISION_ENABLED and OCR_ENABLED first."

    def _analysis_disabled_message(self) -> str:
        if not self._screen_vision_enabled():
            return "Vision is disabled. Enable SCREEN_VISION_ENABLED first."
        if not self.settings.openai_vision_enabled:
            return "OpenAI vision is disabled. Enable OPENAI_VISION_ENABLED first."
        return "Vision analysis is disabled."

    def _screen_vision_enabled(self) -> bool:
        return bool(self.settings.vision_enabled or getattr(self.settings, "screen_vision_enabled", False))

    def _screenshot_ready(self) -> bool:
        return bool(self.settings.screenshot_enabled or getattr(self.settings, "screen_vision_enabled", False))

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

    @staticmethod
    def _image_dependency_available() -> bool:
        try:
            from PIL import Image  # noqa: F401
        except Exception:
            return False
        return True

    @staticmethod
    def _is_supported_image(image_path: Path) -> bool:
        try:
            from PIL import Image
        except Exception:
            return False

        try:
            with Image.open(image_path) as image:
                image.verify()
            return True
        except Exception:
            return False

    def _validate_analysis_path(self, image_path: Path) -> tuple[Path | None, str | None]:
        candidate = Path(image_path).expanduser()
        try:
            resolved = candidate.resolve(strict=False)
        except Exception:
            return None, "The image file cannot be resolved safely."

        path_safety_error = self._scan_text_for_sensitive_keywords(str(resolved))
        if path_safety_error is not None:
            return None, path_safety_error

        if not self._is_path_allowed(resolved):
            return None, "The image path is not in an allowed location."

        if not resolved.exists() or not resolved.is_file():
            return None, "The image file does not exist."

        return resolved, None

    def _is_path_allowed(self, path: Path) -> bool:
        allowed_roots = {self.settings.screenshot_save_dir.resolve(), *self.allowed_image_roots}
        if not allowed_roots:
            return False

        for root in allowed_roots:
            try:
                if path == root or path.is_relative_to(root):
                    return True
            except Exception:
                if str(path).startswith(str(root)):
                    return True
        return False

    def _screen_image_for_sensitive_content(self, image_path: Path) -> str | None:
        path_keywords = self._scan_text_for_sensitive_keywords(str(image_path))
        if path_keywords is not None:
            return path_keywords

        if not self._ocr_dependency_available():
            return None

        try:
            extracted = extract_text_from_image(image_path, max_output_chars=min(self.settings.ocr_max_output_chars, 10000), reader=self.ocr_reader)
        except Exception:
            return None

        if extracted.safe_error is not None and not extracted.success:
            return None

        return self._scan_text_for_sensitive_keywords(extracted.text)

    @staticmethod
    def _scan_text_for_sensitive_keywords(text: str) -> str | None:
        normalized = " ".join(text.lower().split())
        keywords = (
            "password",
            "passcode",
            "pin",
            "bank",
            "banking",
            "credit card",
            "debit card",
            "card number",
            "account number",
            "routing number",
            "ssn",
            "social security",
            "otp",
            "one-time code",
            "verification code",
            "cvv",
            "secret",
            "login",
            "sign in",
        )
        if any(keyword in normalized for keyword in keywords):
            return "The image appears to contain sensitive content and will not be analyzed."
        return None

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
        f"OpenAI vision enabled: {'yes' if report.openai_vision_enabled else 'no'}",
        f"OpenAI API key detected: {'yes' if report.openai_api_key_detected else 'no'}",
        f"Screenshot save dir: {report.screenshot_save_dir}",
        f"OCR provider: {report.ocr_provider}",
        f"OpenAI vision model: {report.openai_vision_model}",
        f"OpenAI vision max image bytes: {report.openai_vision_max_image_bytes}",
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
    if result.monitor_label:
        lines.extend(["", f"Monitor: {result.monitor_label}"])
    if result.image_size:
        lines.extend(["", f"Image size: {result.image_size[0]}x{result.image_size[1]}"])
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
    if result.tesseract_path:
        lines.append(f"Tesseract path: {result.tesseract_path}")
    if result.image_size:
        lines.append(f"Image size: {result.image_size[0]}x{result.image_size[1]}")
    if result.monitor_label:
        lines.append(f"Monitor: {result.monitor_label}")
    if result.text:
        lines.extend(["", "Result:", f"  {result.text}"])
    if result.safe_error:
        lines.extend(["", "Error:", f"  {result.safe_error}"])
    if result.image_path:
        lines.extend(["", f"Image path: {result.image_path}"])
    return "\n".join(lines)


def format_vision_analysis_result(result: VisionAnalysisResult) -> str:
    lines = [
        "Jarvis Vision Analysis",
        "======================",
        f"Vision enabled: {'yes' if result.enabled else 'no'}",
        f"OpenAI vision enabled: {'yes' if result.openai_vision_enabled else 'no'}",
        f"Provider: {result.provider}",
        f"Request attempted: {'yes' if result.request_attempted else 'no'}",
        f"Provider available: {'yes' if result.provider_available else 'no'}",
        f"Diagnostic log: {result.log_file}",
    ]
    if result.monitor_label:
        lines.append(f"Monitor: {result.monitor_label}")
    if result.image_size:
        lines.append(f"Image size: {result.image_size[0]}x{result.image_size[1]}")
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
