from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from aiautomouse.engine.results import Rect

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SW_RESTORE = 9
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0


@dataclass(frozen=True)
class VirtualScreen:
    left: int
    top: int
    width: int
    height: int

    @property
    def rect(self) -> Rect:
        return Rect(self.left, self.top, self.width, self.height)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    rect: Rect

    def to_dict(self) -> dict[str, object]:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "class_name": self.class_name,
            "rect": self.rect.to_dict(),
        }


def get_virtual_screen() -> VirtualScreen:
    user32 = ctypes.windll.user32
    return VirtualScreen(
        left=user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        top=user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        width=user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        height=user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def normalize_region(region) -> Rect | None:
    if region is None:
        return None
    if isinstance(region, Rect):
        return region
    if isinstance(region, (tuple, list)) and len(region) == 4:
        left, top, width, height = [int(value) for value in region]
        return Rect(left, top, width, height)
    if isinstance(region, dict):
        return Rect(
            int(region["left"]),
            int(region["top"]),
            int(region["width"]),
            int(region["height"]),
        )
    raise ValueError(f"Unsupported region payload: {region!r}")


def get_active_window_title() -> str:
    info = get_active_window_info()
    return info.title if info else ""


def get_active_window_info() -> WindowInfo | None:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if not hwnd:
        return None
    return get_window_info(hwnd)


def get_window_info(hwnd: int) -> WindowInfo | None:
    if not hwnd:
        return None
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return WindowInfo(
        hwnd=int(hwnd),
        title=title_buffer.value,
        class_name=class_buffer.value,
        rect=Rect(
            left=int(rect.left),
            top=int(rect.top),
            width=int(rect.right - rect.left),
            height=int(rect.bottom - rect.top),
        ),
    )


def find_windows(title: str | None = None, title_contains: str | None = None, class_name: str | None = None) -> list[WindowInfo]:
    user32 = ctypes.windll.user32
    windows: list[WindowInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        info = get_window_info(hwnd)
        if info is None:
            return True
        if title and info.title != title:
            return True
        if title_contains and title_contains.lower() not in info.title.lower():
            return True
        if class_name and info.class_name != class_name:
            return True
        windows.append(info)
        return True

    user32.EnumWindows(callback, 0)
    return windows


def set_foreground_window(hwnd: int) -> bool:
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_RESTORE)
    return bool(user32.SetForegroundWindow(hwnd))


def get_cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def physical_to_absolute(x: int, y: int) -> tuple[int, int]:
    screen = get_virtual_screen()
    width = max(1, screen.width - 1)
    height = max(1, screen.height - 1)
    absolute_x = int(((x - screen.left) * 65535) / width)
    absolute_y = int(((y - screen.top) * 65535) / height)
    return absolute_x, absolute_y


def get_monitor_dpi_for_point(x: int, y: int) -> int:
    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)
    if shcore is None:
        return 96
    point = wintypes.POINT(x, y)
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    if not monitor:
        return 96
    dpi_x = wintypes.UINT()
    dpi_y = wintypes.UINT()
    try:
        result = shcore.GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
    except Exception:
        return 96
    if result != 0:
        return 96
    return int(dpi_x.value or 96)


def get_monitor_scale_factor_for_rect(rect: Rect) -> float:
    center_x, center_y = rect.center
    return get_monitor_dpi_for_point(center_x, center_y) / 96.0


class WindowManager:
    def get_active_window_title(self) -> str:
        return get_active_window_title()

    def get_active_window_info(self) -> dict[str, object]:
        info = get_active_window_info()
        return info.to_dict() if info else {}

    def get_virtual_screen(self) -> VirtualScreen:
        return get_virtual_screen()

    def normalize_region(self, region) -> Rect | None:
        return normalize_region(region)

    def get_monitor_dpi_for_point(self, x: int, y: int) -> int:
        return get_monitor_dpi_for_point(x, y)

    def get_monitor_scale_factor_for_rect(self, rect: Rect) -> float:
        return get_monitor_scale_factor_for_rect(rect)

    def find_window(self, title: str | None = None, title_contains: str | None = None, class_name: str | None = None) -> WindowInfo | None:
        matches = find_windows(title=title, title_contains=title_contains, class_name=class_name)
        return matches[0] if matches else None

    def focus_window(self, title: str | None = None, title_contains: str | None = None, class_name: str | None = None) -> dict[str, object] | None:
        window = self.find_window(title=title, title_contains=title_contains, class_name=class_name)
        if window is None:
            return None
        set_foreground_window(window.hwnd)
        return window.to_dict()
