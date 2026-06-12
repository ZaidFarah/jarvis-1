from __future__ import annotations

from pathlib import Path

from assistant.core import AssistantCore
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from services.openai_service import OpenAIChatResult
from vision.vision_service import VisionService, format_ocr_result, format_screenshot_result, format_vision_check_report


class FakeOpenAIService:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def chat(self, user_text: str, system_prompt: str | None = None, conversation_history: str | None = None):
        self.messages.append(user_text)
        del system_prompt, conversation_history
        return OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True)


class FakeScreenshotImage:
    def __init__(self, captured_paths: list[Path]) -> None:
        self.captured_paths = captured_paths

    def save(self, path) -> None:
        output_path = Path(path)
        output_path.write_bytes(b"fake-image")
        self.captured_paths.append(output_path)


def _approve(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=log_file)


def _deny(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", log_file=log_file)


def test_vision_disabled_fallback() -> None:
    service = VisionService(AppSettings(_env_file=None))

    report = service.run_check()

    assert report.enabled is False
    assert "Vision is disabled" in report.text


def test_screenshot_disabled_fallback() -> None:
    service = VisionService(AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=False))

    result = service.capture_screenshot()

    assert result.success is False
    assert "Screenshot capture is disabled" in result.text


def test_screenshot_confirmation_denied_blocks_capture(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=True, screenshot_save_dir=tmp_path / "shots")
    captured: list[Path] = []

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _deny(*args, log_file=tmp_path / "confirmations.log"),
        screenshot_capturer=lambda: FakeScreenshotImage(captured),
    )

    result = service.capture_screenshot()

    assert result.success is False
    assert result.text == "Denied."
    assert captured == []


def test_screenshot_save_path_restricted(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=True, screenshot_save_dir=tmp_path / "shots")
    captured: list[Path] = []

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        screenshot_capturer=lambda: FakeScreenshotImage(captured),
    )

    result = service.capture_screenshot()

    assert result.success is True
    assert result.screenshot_path is not None
    assert result.screenshot_path.parent == settings.screenshot_save_dir
    assert result.screenshot_path.exists()
    assert captured and captured[0].parent == settings.screenshot_save_dir
    assert "Screenshot saved to" in format_screenshot_result(result)


def test_ocr_unavailable_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake-image")
    settings = AppSettings(_env_file=None, vision_enabled=True, ocr_enabled=True)

    def reader(_: Path) -> str:
        raise RuntimeError("Tesseract missing")

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        ocr_reader=reader,
    )

    result = service.ocr_image(image_path)

    assert result.success is False
    assert "OCR is unavailable" in result.text
    assert result.safe_error is not None


def test_ocr_output_truncation(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake-image")
    settings = AppSettings(_env_file=None, vision_enabled=True, ocr_enabled=True, ocr_max_output_chars=32)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        ocr_reader=lambda _: "x" * 200,
    )

    result = service.ocr_image(image_path)

    assert result.success is True
    assert result.output_truncated is True
    assert len(result.text) <= 32
    assert "truncated" in format_ocr_result(result).lower()


def test_assistant_core_routes_vision_commands(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        openai_enabled=False,
        vision_enabled=True,
        screenshot_enabled=True,
        ocr_enabled=True,
        screenshot_save_dir=tmp_path / "shots",
        ocr_max_output_chars=64,
    )
    confirmations: list[str] = []

    def approve(action_name: str, risk_level: str, description: str) -> ConfirmationResult:
        confirmations.append(action_name)
        return ConfirmationResult(
            approved=True,
            denied=False,
            timed_out=False,
            reason="Approved.",
            log_file=tmp_path / "confirmations.log",
        )

    captured: list[Path] = []
    vision_service = VisionService(
        settings,
        confirmation_handler=approve,
        screenshot_capturer=lambda: FakeScreenshotImage(captured),
        ocr_reader=lambda _: "screen text",
    )
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), vision_service=vision_service)

    screenshot_response = assistant.handle_command("take screenshot")
    screen_text_response = assistant.handle_command("read screen text")

    assert screenshot_response.source == "vision"
    assert screenshot_response.accepted is True
    assert "Screenshot saved to" in screenshot_response.text
    assert screen_text_response.source == "vision"
    assert screen_text_response.accepted is True
    assert screen_text_response.text == "screen text"
    assert confirmations.count("take screenshot") == 2
    assert confirmations.count("read screen text") == 1
    assert captured
    assert assistant.openai_service.messages == []


def test_vision_no_openai_upload(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=True, ocr_enabled=True)
    openai_service = FakeOpenAIService()

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        screenshot_capturer=lambda: FakeScreenshotImage([]),
        ocr_reader=lambda _: "screen text",
    )
    assistant = AssistantCore(settings=settings, openai_service=openai_service, vision_service=service)

    response = assistant.handle_command("take screenshot")

    assert response.source == "vision"
    assert openai_service.messages == []
