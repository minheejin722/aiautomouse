from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MODIFIER_MAP = {
    "ALT": MOD_ALT,
    "CTRL": MOD_CONTROL,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN,
}

KEY_MAP = {
    "PAUSE": 0x13,
    "SPACE": 0x20,
    "TAB": 0x09,
    "ENTER": 0x0D,
    "ESC": 0x1B,
}


@dataclass(frozen=True)
class HotkeyBinding:
    hotkey: str
    macro: str
    mode: str = "execute"


def parse_hotkey(hotkey: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in hotkey.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"Hotkey must include modifiers and key: {hotkey}")
    modifiers = 0
    for part in parts[:-1]:
        try:
            modifiers |= MODIFIER_MAP[part]
        except KeyError as exc:
            raise ValueError(f"Unsupported modifier: {part}") from exc
    key = parts[-1]
    return modifiers, _key_to_vk(key)


def _key_to_vk(key: str) -> int:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    if key.startswith("F") and key[1:].isdigit():
        return 0x70 + int(key[1:]) - 1
    if key in KEY_MAP:
        return KEY_MAP[key]
    raise ValueError(f"Unsupported hotkey key: {key}")


class GlobalHotkeyService:
    def __init__(self) -> None:
        self._pending: list[tuple[str, callable]] = []
        self._callbacks: dict[int, callable] = {}
        self._thread_id: int | None = None
        self._ready = threading.Event()

    def add_binding(self, hotkey: str, callback) -> None:
        self._pending.append((hotkey, callback))

    def run_forever(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        registration_id = 1
        try:
            for hotkey, callback in self._pending:
                modifiers, vk = parse_hotkey(hotkey)
                if not user32.RegisterHotKey(None, registration_id, modifiers, vk):
                    raise OSError(f"Failed to register hotkey: {hotkey}")
                self._callbacks[registration_id] = callback
                registration_id += 1
            self._ready.set()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
                if message.message == WM_HOTKEY:
                    callback = self._callbacks.get(int(message.wParam))
                    if callback is not None:
                        threading.Thread(target=callback, daemon=True).start()
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            for hotkey_id in list(self._callbacks):
                user32.UnregisterHotKey(None, hotkey_id)
            self._callbacks.clear()
            self._ready.set()

    def wait_until_ready(self, timeout: float = 2.0) -> bool:
        return self._ready.wait(timeout)

    def stop(self) -> None:
        if self._thread_id is None:
            return
        ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

