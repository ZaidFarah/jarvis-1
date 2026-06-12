from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ScreenshotCaptureError(RuntimeError):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


ScreenshotCapturer = Callable[[], Any]


def capture_screenshot_image(
    save_dir: Path,
    capturer: ScreenshotCapturer | None = None,
) -> Path:
    save_dir.mkdir(parents=True, exist_ok=True)
    screenshot = capturer() if capturer is not None else _default_capturer()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_path = save_dir / f"vision-screenshot-{timestamp}.png"
    try:
        screenshot.save(output_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise ScreenshotCaptureError("Unable to save the screenshot image.") from exc
    return output_path


def _default_capturer() -> Any:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ScreenshotCaptureError(
            "Pillow is required for screenshot capture. Install Pillow to enable screenshots."
        ) from exc

    try:
        return ImageGrab.grab()
    except Exception as exc:
        raise ScreenshotCaptureError("Screenshot capture is unavailable on this system.") from exc
