from __future__ import annotations

import threading

from aiautomouse.platform.win32_hotkeys import GlobalHotkeyService
from aiautomouse.runtime.emergency_stop import EmergencyStopToken


class HotkeyServiceController:
    def __init__(self, automation_app, hotkey_repository) -> None:
        self.automation_app = automation_app
        self.hotkey_repository = hotkey_repository
        self._service: GlobalHotkeyService | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.is_running():
                return
            bindings = self.hotkey_repository.load_bindings()
            service = GlobalHotkeyService()
            for binding in bindings:
                service.add_binding(binding.hotkey, lambda binding=binding: self._run_binding(binding))
            service.add_binding(self.automation_app.settings.emergency_stop_hotkey, self.automation_app.trigger_emergency_stop)
            thread = threading.Thread(target=service.run_forever, daemon=True)
            thread.start()
            service.wait_until_ready()
            self._service = service
            self._thread = thread

    def stop(self) -> None:
        with self._lock:
            if self._service is not None:
                self._service.stop()
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            self._service = None
            self._thread = None

    def reload(self) -> None:
        self.stop()
        self.start()

    def _run_binding(self, binding) -> None:
        token = EmergencyStopToken()

        def target() -> None:
            self.automation_app.run_macro(binding.macro, mode=binding.mode, stop_token=token, start_emergency_watcher=False)

        threading.Thread(target=target, daemon=True).start()
