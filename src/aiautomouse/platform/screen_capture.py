from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from PIL import ImageGrab

from aiautomouse.engine.results import Rect
from aiautomouse.platform.win32_windows import WindowManager


@dataclass
class CaptureFrame:
    image: Image.Image
    rect: Rect
    screenshot_id: str
    source: str
    metadata: dict[str, object] = field(default_factory=dict)
    _fingerprint: str | None = field(default=None, init=False, repr=False)

    def fingerprint(self) -> str:
        if self._fingerprint is None:
            digest = hashlib.sha1()
            digest.update(f"{self.source}:{self.rect.left}:{self.rect.top}:{self.rect.width}:{self.rect.height}".encode("utf-8"))
            digest.update(self.image.tobytes())
            self._fingerprint = digest.hexdigest()
        return self._fingerprint


class ScreenCapture:
    def __init__(self, window_manager: WindowManager | None = None, backend: str = "mss") -> None:
        self.window_manager = window_manager or WindowManager()
        self.backend = backend.lower()
        try:
            import mss  # type: ignore
        except Exception:
            mss = None
        self._mss_module = mss
        try:
            import dxcam  # type: ignore
        except Exception:
            dxcam = None
        self._dxcam_module = dxcam
        self._dxcam_camera = None

    def capture(self, region=None) -> Image.Image:
        return self.capture_frame(region=region).image

    def capture_with_rect(self, region=None) -> tuple[Image.Image, Rect]:
        frame = self.capture_frame(region=region)
        return frame.image, frame.rect

    def capture_frame(
        self,
        region=None,
        *,
        monitor_index: int | None = None,
        window=None,
        reason: str = "capture",
    ) -> CaptureFrame:
        rect, source, metadata = self._resolve_capture_target(region=region, monitor_index=monitor_index, window=window)
        image = self._capture_rect(rect)
        screenshot_id = f"{reason}_{uuid.uuid4().hex[:12]}"
        return CaptureFrame(
            image=image,
            rect=rect,
            screenshot_id=screenshot_id,
            source=source,
            metadata=metadata,
        )

    def save(self, image: Image.Image, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        return destination

    def close(self) -> None:
        if self._dxcam_camera is not None:
            stop = getattr(self._dxcam_camera, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
        self._dxcam_camera = None

    def describe_capture_target(self, *, region=None, monitor_index: int | None = None, window=None) -> tuple[Rect, str, dict[str, object]]:
        return self._resolve_capture_target(region=region, monitor_index=monitor_index, window=window)

    def _resolve_capture_target(self, *, region=None, monitor_index: int | None = None, window=None) -> tuple[Rect, str, dict[str, object]]:
        rect = self.window_manager.normalize_region(region)
        if rect is not None:
            return rect, "region", {}
        if monitor_index is not None:
            return self._monitor_rect(monitor_index), "monitor", {"monitor_index": monitor_index}
        if window is not None:
            return self._window_rect(window), "window", {}
        return self.window_manager.get_virtual_screen().rect, "full_screen", {}

    def _capture_rect(self, rect: Rect) -> Image.Image:
        if self.backend == "dxcam":
            image = self._capture_with_dxcam(rect)
            if image is not None:
                return image
        if self._mss_module is not None:
            with self._mss_module.mss() as sct:
                frame = sct.grab(
                    {
                        "left": rect.left,
                        "top": rect.top,
                        "width": rect.width,
                        "height": rect.height,
                    }
                )
                return Image.frombytes("RGB", frame.size, frame.rgb)
        bbox = (rect.left, rect.top, rect.right, rect.bottom)
        return ImageGrab.grab(bbox=bbox, all_screens=True)

    def _capture_with_dxcam(self, rect: Rect) -> Image.Image | None:
        if self._dxcam_module is None:
            return None
        if self._dxcam_camera is None:
            self._dxcam_camera = self._dxcam_module.create(output_color="RGB")
        frame = self._dxcam_camera.grab(region=(rect.left, rect.top, rect.right, rect.bottom))
        if frame is None:
            return None
        return Image.fromarray(frame)

    def _monitor_rect(self, monitor_index: int) -> Rect:
        if monitor_index < 0:
            raise ValueError("monitor_index must be >= 0")
        if self._mss_module is not None:
            with self._mss_module.mss() as sct:
                monitors = sct.monitors[1:]
                if monitor_index >= len(monitors):
                    raise ValueError(f"monitor_index {monitor_index} is out of range")
                monitor = monitors[monitor_index]
                return Rect(
                    left=int(monitor["left"]),
                    top=int(monitor["top"]),
                    width=int(monitor["width"]),
                    height=int(monitor["height"]),
                )
        if monitor_index == 0:
            return self.window_manager.get_virtual_screen().rect
        raise ValueError("monitor capture requires mss when selecting non-primary monitors")

    def _window_rect(self, window) -> Rect:
        raw_rect = None
        if isinstance(window, dict):
            raw_rect = window.get("rect")
        else:
            raw_rect = getattr(window, "rect", None)
        rect = self.window_manager.normalize_region(raw_rect)
        if rect is not None:
            return rect
        locator = {
            "title": window.get("title") if isinstance(window, dict) else getattr(window, "title", None),
            "title_contains": window.get("title_contains") if isinstance(window, dict) else getattr(window, "title_contains", None),
            "class_name": window.get("class_name") if isinstance(window, dict) else getattr(window, "class_name", None),
        }
        found = self.window_manager.find_window(
            title=locator["title"],
            title_contains=locator["title_contains"],
            class_name=locator["class_name"],
        )
        if found is None:
            raise ValueError("window capture target not found")
        return found.rect
