from __future__ import annotations

import threading

from aiautomouse.platform.win32_hotkeys import GlobalHotkeyService


class EmergencyStopToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def trigger(self) -> None:
        self._event.set()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


class EmergencyStopWatcher:
    def __init__(self, hotkey: str, token: EmergencyStopToken) -> None:
        self.hotkey = hotkey
        self.token = token
        self.service = GlobalHotkeyService()
        self.service.add_binding(hotkey, self.token.trigger)
        self.thread = threading.Thread(target=self.service.run_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()
        self.service.wait_until_ready()

    def stop(self) -> None:
        self.service.stop()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

