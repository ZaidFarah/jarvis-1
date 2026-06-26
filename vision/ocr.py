from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


OCRReader = Callable[[Path], str]


@dataclass(frozen=True)
class OCRExtractionResult:
    success: bool
    text: str
    provider: str
    image_path: Path
    output_truncated: bool
    provider_available: bool
    tesseract_path: str | None = None
    image_size: tuple[int, int] | None = None
    image_mode: str | None = None
    safe_error: str | None = None


def extract_text_from_image(
    image_path: Path,
    max_output_chars: int,
    reader: OCRReader | None = None,
) -> OCRExtractionResult:
    image_path = Path(image_path)
    if not image_path.exists() or not image_path.is_file():
        return OCRExtractionResult(
            success=False,
            text="The image file does not exist.",
            provider="tesseract",
            image_path=image_path,
            output_truncated=False,
            provider_available=False,
            tesseract_path=_tesseract_path(),
            safe_error="Image file does not exist.",
        )

    image_size, image_mode = _inspect_image(image_path)

    try:
        raw_text = reader(image_path) if reader is not None else _default_reader(image_path)
    except Exception as exc:
        safe_error = _format_ocr_error(exc)
        return OCRExtractionResult(
            success=False,
            text="OCR is unavailable right now.",
            provider="tesseract",
            image_path=image_path,
            output_truncated=False,
            provider_available=False,
            tesseract_path=_tesseract_path(),
            image_size=image_size,
            image_mode=image_mode,
            safe_error=safe_error,
        )

    cleaned = _normalize_text(raw_text)
    truncated = False
    if len(cleaned) > max_output_chars:
        suffix = " [truncated]"
        limit = max(0, max_output_chars - len(suffix))
        cleaned = cleaned[:limit].rstrip() + suffix
        truncated = True

    return OCRExtractionResult(
        success=True,
        text=cleaned,
        provider="tesseract",
        image_path=image_path,
        output_truncated=truncated,
        provider_available=True,
        tesseract_path=_tesseract_path(),
        image_size=image_size,
        image_mode=image_mode,
    )


def _default_reader(image_path: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Pillow and pytesseract are required for OCR. Install them to enable screen text reading."
        ) from exc

    try:
        with Image.open(image_path) as image:
            return pytesseract.image_to_string(image)
    except Exception as exc:
        raise RuntimeError("OCR failed for the provided image.") from exc


def _inspect_image(image_path: Path) -> tuple[tuple[int, int] | None, str | None]:
    try:
        from PIL import Image
    except Exception:
        return None, None

    try:
        with Image.open(image_path) as image:
            return image.size, image.mode
    except Exception:
        return None, None


def _tesseract_path() -> str | None:
    try:
        import pytesseract
    except Exception:
        return shutil.which("tesseract")
    configured = getattr(pytesseract.pytesseract, "tesseract_cmd", "") or ""
    if configured:
        return configured
    return shutil.which("tesseract")


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\x0c", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return cleaned


def _format_ocr_error(error: Exception) -> str:
    error_type = type(error).__name__
    message = str(error).strip() or "No error details provided."
    return f"{error_type}: {message}"
