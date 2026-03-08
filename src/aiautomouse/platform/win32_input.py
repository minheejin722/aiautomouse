from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from aiautomouse.platform.win32_windows import physical_to_absolute

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

VK_CODES = {
    "ALT": 0x12,
    "CTRL": 0x11,
    "SHIFT": 0x10,
    "WIN": 0x5B,
    "ENTER": 0x0D,
    "TAB": 0x09,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "PAUSE": 0x13,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


def _send_input(*inputs: INPUT) -> None:
    array_type = INPUT * len(inputs)
    ctypes.windll.user32.SendInput(len(inputs), array_type(*inputs), ctypes.sizeof(INPUT))


def _mouse_input(flags: int, x: int = 0, y: int = 0) -> INPUT:
    return INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(
                dx=x,
                dy=y,
                mouseData=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )
        ),
    )


def _keyboard_input(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=vk,
                wScan=scan,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )
        ),
    )


class Win32InputController:
    def move_mouse(self, x: int, y: int, duration_ms: int = 0) -> None:
        user32 = ctypes.windll.user32
        if duration_ms <= 0:
            user32.SetCursorPos(int(x), int(y))
            return
        start_x, start_y = self.get_cursor_position()
        steps = max(2, duration_ms // 15)
        for index in range(1, steps + 1):
            progress = index / steps
            current_x = int(start_x + (x - start_x) * progress)
            current_y = int(start_y + (y - start_y) * progress)
            user32.SetCursorPos(current_x, current_y)
            time.sleep(duration_ms / steps / 1000.0)

    def click(self, x: int | None, y: int | None, button: str = "left") -> None:
        if x is not None and y is not None:
            self.move_mouse(x, y)
        down, up = self._mouse_button_flags(button)
        _send_input(_mouse_input(down), _mouse_input(up))

    def double_click(self, x: int | None, y: int | None, button: str = "left") -> None:
        self.click(x, y, button=button)
        time.sleep(0.05)
        self.click(x, y, button=button)

    def type_text(self, text: str) -> None:
        for char in text:
            scan = ord(char)
            _send_input(
                _keyboard_input(scan=scan, flags=KEYEVENTF_UNICODE),
                _keyboard_input(scan=scan, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
            )

    def paste_text(self, text: str) -> None:
        self.set_clipboard_text(text)
        self.hotkey(["CTRL", "V"])

    def hotkey(self, keys: list[str]) -> None:
        normalized = [key.upper() for key in keys]
        if not normalized:
            return
        modifiers = normalized[:-1]
        terminal = normalized[-1]
        for key in modifiers:
            _send_input(_keyboard_input(vk=self._vk_for_key(key)))
        terminal_vk = self._vk_for_key(terminal)
        _send_input(
            _keyboard_input(vk=terminal_vk),
            _keyboard_input(vk=terminal_vk, flags=KEYEVENTF_KEYUP),
        )
        for key in reversed(modifiers):
            _send_input(_keyboard_input(vk=self._vk_for_key(key), flags=KEYEVENTF_KEYUP))

    def set_clipboard_text(self, text: str) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(None):
            return
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            pointer = kernel32.GlobalLock(handle)
            ctypes.memmove(pointer, data, len(data))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(CF_UNICODETEXT, handle)
        finally:
            user32.CloseClipboard()

    def get_clipboard_text(self) -> str | None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(None):
            return None
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return None
            try:
                return ctypes.wstring_at(pointer)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def get_cursor_position(self) -> tuple[int, int]:
        point = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def move_mouse_absolute(self, x: int, y: int) -> None:
        absolute_x, absolute_y = physical_to_absolute(x, y)
        _send_input(
            _mouse_input(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                absolute_x,
                absolute_y,
            )
        )

    def _mouse_button_flags(self, button: str) -> tuple[int, int]:
        normalized = button.lower()
        if normalized == "right":
            return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    def _vk_for_key(self, key: str) -> int:
        if len(key) == 1 and key.isalpha():
            return ord(key.upper())
        if len(key) == 1 and key.isdigit():
            return ord(key)
        if key.startswith("F") and key[1:].isdigit():
            return 0x70 + int(key[1:]) - 1
        if key in VK_CODES:
            return VK_CODES[key]
        raise ValueError(f"Unsupported hotkey token: {key}")
