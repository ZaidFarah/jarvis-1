from __future__ import annotations

from pathlib import Path

from assistant.core import AssistantCore
from config.settings import AppSettings
from security.confirmation import ConfirmationResult
from services.openai_service import OpenAIChatResult, OpenAIVisionResult
from vision.vision_service import (
    VisionService,
    format_ocr_result,
    format_screenshot_result,
    format_vision_analysis_result,
    format_vision_check_report,
)


class FakeOpenAIService:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.vision_requests: list[Path] = []

    def chat(self, user_text: str, system_prompt: str | None = None, conversation_history: str | None = None):
        self.messages.append(user_text)
        del system_prompt, conversation_history
        return OpenAIChatResult(success=True, text="OpenAI answer", used_openai=True)

    def analyze_image(self, image_path: Path, prompt: str, system_prompt: str | None = None):
        self.vision_requests.append(Path(image_path))
        del prompt, system_prompt
        return OpenAIVisionResult(
            success=True,
            text="OpenAI vision answer",
            used_openai=True,
            image_path=Path(image_path),
            model="gpt-4o-mini",
            request_attempted=True,
            provider_available=True,
        )


class FakeScreenshotImage:
    def __init__(self, captured_paths: list[Path]) -> None:
        self.captured_paths = captured_paths

    def save(self, path) -> None:
        output_path = Path(path)
        from PIL import Image

        image = Image.new("RGB", (8, 8), color=(255, 255, 255))
        image.save(output_path)
        self.captured_paths.append(output_path)


def _approve(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=True, denied=False, timed_out=False, reason="Approved.", log_file=log_file)


def _deny(action_name: str, risk_level: str, description: str, log_file: Path) -> ConfirmationResult:
    del action_name, risk_level, description
    return ConfirmationResult(approved=False, denied=True, timed_out=False, reason="Denied.", log_file=log_file)


def _write_png(path: Path) -> None:
    from PIL import Image

    image = Image.new("RGB", (8, 8), color=(255, 255, 255))
    image.save(path)


def test_vision_disabled_fallback() -> None:
    service = VisionService(AppSettings(_env_file=None))

    report = service.run_check()

    assert report.enabled is False
    assert "Vision is disabled" in report.text


def test_vision_check_reports_openai_vision_defaults() -> None:
    report = VisionService(AppSettings(_env_file=None, vision_enabled=True)).run_check()

    assert report.openai_vision_enabled is False
    assert report.openai_vision_model == "gpt-4o-mini"
    assert "OpenAI vision" in format_vision_check_report(report)


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


def test_openai_vision_disabled_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake-image")
    settings = AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=False)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )

    result = service.analyze_image(image_path)

    assert result.success is False
    assert "OpenAI vision is disabled" in result.text


def test_confirmation_denied_before_screenshot(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=True, openai_vision_enabled=True, screenshot_save_dir=tmp_path / "shots")
    captured: list[Path] = []

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _deny(*args, log_file=tmp_path / "confirmations.log"),
        screenshot_capturer=lambda: FakeScreenshotImage(captured),
        openai_service=FakeOpenAIService(),
    )

    result = service.capture_screenshot()

    assert result.success is False
    assert captured == []


def test_confirmation_denied_before_openai_upload(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    _write_png(image_path)
    settings = AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=True)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _deny(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )

    result = service.analyze_image(image_path)

    assert result.success is False
    assert "Denied." in result.text


def test_oversized_image_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    from PIL import Image

    image = Image.new("RGB", (256, 256))
    for x in range(256):
        for y in range(256):
            image.putpixel((x, y), ((x * 7) % 256, (y * 11) % 256, ((x + y) * 13) % 256))
    image.save(image_path, compress_level=0)
    settings = AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=True, openai_vision_max_image_bytes=1024)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )

    result = service.analyze_image(image_path)

    assert result.success is False
    assert "too large" in result.text.lower()


def test_non_image_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.txt"
    image_path.write_text("not an image", encoding="utf-8")
    settings = AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=True)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )

    result = service.analyze_image(image_path)

    assert result.success is False
    assert "only image files" in result.text.lower()


def test_unsafe_keyword_blocked(tmp_path: Path) -> None:
    image_path = tmp_path / "bank-password-screen.png"
    image_path.write_bytes(b"fake-image")
    settings = AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=True)

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )

    result = service.analyze_image(image_path)

    assert result.success is False
    assert "sensitive content" in result.text.lower()


def test_assistant_core_routes_vision_commands(tmp_path: Path) -> None:
    settings = AppSettings(
        _env_file=None,
        openai_enabled=False,
        vision_enabled=True,
        screenshot_enabled=True,
        ocr_enabled=True,
        openai_vision_enabled=True,
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
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )
    assistant = AssistantCore(settings=settings, openai_service=FakeOpenAIService(), vision_service=vision_service)

    screenshot_response = assistant.handle_command("take screenshot")
    screen_text_response = assistant.handle_command("read screen text")
    analyze_response = assistant.handle_command("analyze screenshot")

    assert screenshot_response.source == "vision"
    assert screenshot_response.accepted is True
    assert "Screenshot saved to" in screenshot_response.text
    assert screen_text_response.source == "vision"
    assert screen_text_response.accepted is True
    assert screen_text_response.text == "screen text"
    assert analyze_response.source == "vision"
    assert analyze_response.accepted is True
    assert "OpenAI vision answer" in analyze_response.text
    assert confirmations.count("take screenshot") == 3
    assert confirmations.count("read screen text") == 1
    assert confirmations.count("send image to openai") == 1
    assert captured
    assert assistant.openai_service.messages == []
    assert assistant.conversation_history.format_recent_history() == ""
    assert vision_service.openai_service.vision_requests


def test_vision_no_openai_upload(tmp_path: Path) -> None:
    settings = AppSettings(_env_file=None, vision_enabled=True, screenshot_enabled=True, ocr_enabled=True, openai_vision_enabled=True)
    openai_service = FakeOpenAIService()

    service = VisionService(
        settings,
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        screenshot_capturer=lambda: FakeScreenshotImage([]),
        ocr_reader=lambda _: "screen text",
        openai_service=openai_service,
        allowed_image_roots={tmp_path},
    )
    assistant = AssistantCore(settings=settings, openai_service=openai_service, vision_service=service)

    response = assistant.handle_command("analyze screenshot")

    assert response.source == "vision"
    assert openai_service.messages == []
    assert openai_service.vision_requests
    assert "OpenAI vision answer" in response.text
    assert assistant.conversation_history.format_recent_history() == ""


def test_vision_analyze_formatting(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    image_path.write_bytes(b"fake-image")
    result = VisionService(
        AppSettings(_env_file=None, vision_enabled=True, openai_vision_enabled=True),
        confirmation_handler=lambda *args: _approve(*args, log_file=tmp_path / "confirmations.log"),
        openai_service=FakeOpenAIService(),
        allowed_image_roots={tmp_path},
    )._analysis_result(
        success=True,
        text="OpenAI vision answer",
        image_path=image_path,
        request_attempted=True,
        provider_available=True,
        openai_vision_enabled=True,
    )

    assert "OpenAI vision answer" in format_vision_analysis_result(result)
