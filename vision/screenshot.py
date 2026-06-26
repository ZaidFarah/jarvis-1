from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable


ScreenshotCapturer = Callable[[], Any]
MonitorProvider = Callable[[], list["MonitorInfo"]]


@dataclass(frozen=True)
class ScreenshotCaptureError(RuntimeError):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    left: int
    top: int
    width: int
    height: int
    primary: bool
    name: str | None = None

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    @property
    def label(self) -> str:
        prefix = "Primary screen" if self.primary else f"Screen {self.index}"
        if self.name:
            return f"{prefix} ({self.name})"
        return prefix


@dataclass(frozen=True)
class ScreenshotCaptureDetails:
    image_path: Path
    monitor: MonitorInfo | None
    all_monitors: bool
    monitor_count: int
    image_size: tuple[int, int] | None


def list_monitors(provider: MonitorProvider | None = None) -> list[MonitorInfo]:
    if provider is not None:
        monitors = provider()
        return _normalize_monitors(monitors)

    monitors = _windows_monitors()
    if monitors:
        return _normalize_monitors(monitors)

    fallback_size = _fallback_image_size()
    if fallback_size is not None:
        width, height = fallback_size
        return [
            MonitorInfo(
                index=1,
                left=0,
                top=0,
                width=width,
                height=height,
                primary=True,
                name="Virtual screen",
            )
        ]
    return []


def resolve_monitor_target(
    monitors: Iterable[MonitorInfo],
    monitor: str | int | None = None,
    all_monitors: bool = False,
) -> tuple[MonitorInfo | None, bool]:
    normalized = list(monitors)
    if all_monitors:
        return None, True

    if not normalized:
        return None, False

    if monitor is None:
        return _primary_monitor(normalized), False

    if isinstance(monitor, int):
        index = monitor
    else:
        token = str(monitor).strip().lower()
        if token in {"primary", "main", "default"}:
            return _primary_monitor(normalized), False
        try:
            index = int(token)
        except ValueError:
            return _primary_monitor(normalized), False

    if index <= 0:
        return _primary_monitor(normalized), False

    for item in normalized:
        if item.index == index:
            return item, False

    return _primary_monitor(normalized), False


def capture_screenshot_image(
    save_dir: Path,
    capturer: ScreenshotCapturer | None = None,
    monitor: str | int | None = None,
    all_monitors: bool = False,
    monitor_provider: MonitorProvider | None = None,
) -> Path:
    details = capture_screenshot_details(
        save_dir,
        capturer=capturer,
        monitor=monitor,
        all_monitors=all_monitors,
        monitor_provider=monitor_provider,
    )
    return details.image_path


def capture_screenshot_details(
    save_dir: Path,
    capturer: ScreenshotCapturer | None = None,
    monitor: str | int | None = None,
    all_monitors: bool = False,
    monitor_provider: MonitorProvider | None = None,
) -> ScreenshotCaptureDetails:
    save_dir.mkdir(parents=True, exist_ok=True)
    monitors = list_monitors(monitor_provider)
    selected_monitor, capture_all = resolve_monitor_target(monitors, monitor=monitor, all_monitors=all_monitors)
    screenshot = capturer() if capturer is not None else _default_capturer(selected_monitor, capture_all)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output_path = save_dir / f"vision-screenshot-{timestamp}.png"
    try:
        screenshot.save(output_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise ScreenshotCaptureError("Unable to save the screenshot image.") from exc
    return ScreenshotCaptureDetails(
        image_path=output_path,
        monitor=selected_monitor,
        all_monitors=capture_all,
        monitor_count=len(monitors),
        image_size=_image_size(screenshot),
    )


def _default_capturer(monitor: MonitorInfo | None, all_monitors: bool) -> Any:
    try:
        from PIL import ImageGrab
    except Exception as exc:  # pragma: no cover - optional dependency
        raise ScreenshotCaptureError(
            "Pillow is required for screenshot capture. Install Pillow to enable screenshots."
        ) from exc

    try:
        if all_monitors:
            return ImageGrab.grab(all_screens=True)
        if monitor is not None:
            return ImageGrab.grab(bbox=monitor.bounds)
        return ImageGrab.grab()
    except Exception as exc:
        raise ScreenshotCaptureError("Screenshot capture is unavailable on this system.") from exc


def _image_size(image: Any) -> tuple[int, int] | None:
    width = getattr(image, "width", None)
    height = getattr(image, "height", None)
    if isinstance(width, int) and isinstance(height, int):
        return width, height
    size = getattr(image, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        w, h = size
        if isinstance(w, int) and isinstance(h, int):
            return w, h
    return None


def _primary_monitor(monitors: list[MonitorInfo]) -> MonitorInfo | None:
    for monitor in monitors:
        if monitor.primary:
            return monitor
    return monitors[0] if monitors else None


def _normalize_monitors(monitors: Iterable[MonitorInfo]) -> list[MonitorInfo]:
    normalized = list(monitors)
    if not normalized:
        return []
    normalized.sort(key=lambda item: (not item.primary, item.top, item.left, item.index))
    return [
        MonitorInfo(
            index=index,
            left=item.left,
            top=item.top,
            width=item.width,
            height=item.height,
            primary=item.primary if index == 1 else False,
            name=item.name,
        )
        for index, item in enumerate(normalized, start=1)
    ]


def _windows_monitors() -> list[MonitorInfo]:
    try:
        user32 = ctypes.windll.user32
    except Exception:  # pragma: no cover - non-Windows
        return []

    monitors: list[MonitorInfo] = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_uint),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    MONITORINFOF_PRIMARY = 1

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def callback(hmonitor, hdc, lprect, lparam):  # noqa: ANN001
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            monitors.append(
                MonitorInfo(
                    index=len(monitors) + 1,
                    left=rect.left,
                    top=rect.top,
                    width=rect.right - rect.left,
                    height=rect.bottom - rect.top,
                    primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    name=info.szDevice.strip() or None,
                )
            )
        return 1

    try:
        enum_proc = MonitorEnumProc(callback)
        user32.EnumDisplayMonitors(0, 0, enum_proc, 0)
    except Exception:
        return []
    return monitors


def _fallback_image_size() -> tuple[int, int] | None:
    try:
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        image = ImageGrab.grab()
        return _image_size(image)
    except Exception:
        return None
