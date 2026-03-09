from __future__ import annotations

import contextlib
import threading
import uuid
from pathlib import Path

import yaml

from aiautomouse.bootstrap.dpi import ensure_per_monitor_v2_dpi_awareness
from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.browser.adapter import PlaywrightBrowserAdapter
from aiautomouse.engine.context import RunMode, RuntimeContext
from aiautomouse.engine.loader import load_macro
from aiautomouse.engine.models import CURRENT_SCHEMA_VERSION
from aiautomouse.engine.runner import MacroRunner
from aiautomouse.engine.resolver import TargetResolver
from aiautomouse.engine.schema import MACRO_SCHEMA_ID
from aiautomouse.platform.screen_capture import ScreenCapture
from aiautomouse.platform.win32_hotkeys import GlobalHotkeyService, HotkeyBinding
from aiautomouse.platform.win32_input import Win32InputController
from aiautomouse.platform.win32_windows import WindowManager
from aiautomouse.providers.browser_cdp import BrowserCdpProvider
from aiautomouse.providers.template_match import TemplateMatchProvider
from aiautomouse.providers.windows_ocr import WindowsOcrProvider
from aiautomouse.providers.windows_uia import WindowsUiaProvider
from aiautomouse.resources.snippets import SnippetStore
from aiautomouse.resources.templates import TemplateStore
from aiautomouse.runtime.artifacts import ArtifactManager
from aiautomouse.runtime.emergency_stop import EmergencyStopToken, EmergencyStopWatcher
from aiautomouse.runtime.logging import StructuredEventLogger
from aiautomouse.runtime.overlay import NullOverlay, TkDebugOverlay

DEFAULT_SETTINGS_PATH = Path("config/app.yaml")


class AutomationApplication:
    def __init__(self, settings_path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
        self.settings_path = Path(settings_path)
        self.settings = AppSettings.load(self.settings_path)
        self.dpi_mode = ensure_per_monitor_v2_dpi_awareness()
        self.window_manager = WindowManager()
        self.input_controller = Win32InputController()
        self.screen_capture = ScreenCapture(self.window_manager, backend=self.settings.capture.backend)
        self.runner = MacroRunner()
        self._active_tokens: list[EmergencyStopToken] = []
        self._active_lock = threading.Lock()

    def run_macro(
        self,
        macro_path: str | Path,
        mode: str = RunMode.EXECUTE.value,
        stop_token: EmergencyStopToken | None = None,
        start_emergency_watcher: bool | None = None,
    ):
        macro_file = Path(macro_path).resolve()
        macro = load_macro(macro_file)
        snippets = SnippetStore.from_macro(macro, macro_file)
        templates = TemplateStore.from_macro(macro, macro_file)
        token = stop_token or EmergencyStopToken()
        watcher = None
        browser = self._build_browser_adapter()
        if start_emergency_watcher is None:
            start_emergency_watcher = stop_token is None
        if start_emergency_watcher:
            watcher = EmergencyStopWatcher(self.settings.emergency_stop_hotkey, token)
            watcher.start()

        run_id = uuid.uuid4().hex[:12]
        artifacts = ArtifactManager(self.settings.artifacts_dir / run_id)
        event_logger = StructuredEventLogger(artifacts.events_path, self.settings.log_level)
        overlay = self._build_overlay(artifacts)
        resolver = self._build_resolver(browser)
        context = RuntimeContext(
            settings=self.settings,
            mode=RunMode(mode),
            resolver=resolver,
            artifacts=artifacts,
            event_logger=event_logger,
            overlay=overlay,
            stop_token=token,
            input_controller=self.input_controller,
            window_manager=self.window_manager,
            screen_capture=self.screen_capture,
            browser=browser,
            snippets=snippets,
            templates=templates,
            macro_path=macro_file,
            macro=macro,
            run_id=run_id,
        )

        try:
            with self._track_token(token):
                return self.runner.run(macro, context)
        except Exception as exc:
            with contextlib.suppress(Exception):
                context.refresh_active_window()
            with contextlib.suppress(Exception):
                event_logger.emit(
                    "runtime_crash",
                    macro=macro.name,
                    mode=mode,
                    error=str(exc),
                    active_window=context.active_window_info,
                )
            with contextlib.suppress(Exception):
                artifacts.write_run_summary(
                    {
                        "run_id": run_id,
                        "macro_name": macro.name,
                        "status": "crashed",
                        "error": str(exc),
                        "active_window": context.active_window_info,
                        "failed_step_id": context.state.get("failed_step_id"),
                    }
                )
            raise
        finally:
            with contextlib.suppress(Exception):
                overlay.close()
            with contextlib.suppress(Exception):
                browser.close()
            if watcher is not None:
                with contextlib.suppress(Exception):
                    watcher.stop()
            with contextlib.suppress(Exception):
                event_logger.close()

    def serve_hotkeys(self, hotkeys_path: str | Path) -> None:
        hotkeys = self._load_hotkeys(hotkeys_path)
        service = GlobalHotkeyService()
        for binding in hotkeys:
            service.add_binding(binding.hotkey, lambda binding=binding: self._spawn_bound_macro(binding))
        service.add_binding(self.settings.emergency_stop_hotkey, self.trigger_emergency_stop)
        try:
            service.run_forever()
        finally:
            service.stop()
            self.shutdown()

    def doctor(self) -> dict:
        browser = self._build_browser_adapter()
        resolver = self._build_resolver(browser)
        result = {
            "settings_path": str(self.settings_path.resolve()),
            "dpi_mode": self.dpi_mode,
            "cdp_url": self.settings.browser.cdp_url,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "schema_id": MACRO_SCHEMA_ID,
            "capture_backend": self.settings.capture.backend,
            "logs_dir": str(self.settings.paths.logs_dir.resolve()),
            "artifacts_dir": str(self.settings.paths.artifacts_dir.resolve()),
            "emergency_stop_hotkey": self.settings.emergency_stop_hotkey,
            "ocr_backends": self.settings.ocr.backends,
            "browser": {
                "launch_on_demand": self.settings.browser.launch_on_demand,
                "channel": self.settings.browser.channel,
                "headless": self.settings.browser.headless,
            },
            "virtual_screen": self.window_manager.get_virtual_screen().__dict__,
            "providers": {
                provider.name: provider.is_available() for provider in resolver.providers
            },
        }
        browser.close()
        return result

    def trigger_emergency_stop(self) -> None:
        with self._active_lock:
            for token in list(self._active_tokens):
                token.trigger()

    def shutdown(self) -> None:
        self.trigger_emergency_stop()
        with contextlib.suppress(Exception):
            self.screen_capture.close()

    def _spawn_bound_macro(self, binding: HotkeyBinding) -> None:
        token = EmergencyStopToken()

        def target() -> None:
            self.run_macro(binding.macro, mode=binding.mode, stop_token=token, start_emergency_watcher=False)

        threading.Thread(target=target, daemon=True).start()

    def _build_resolver(self, browser: PlaywrightBrowserAdapter) -> TargetResolver:
        providers = [
            BrowserCdpProvider(browser),
            WindowsUiaProvider(),
            WindowsOcrProvider(
                backends=self.settings.ocr.backends,
                tesseract_cmd=self.settings.ocr.tesseract_cmd,
                easyocr_languages=self.settings.ocr.easyocr_languages,
                easyocr_gpu=self.settings.ocr.easyocr_gpu,
                rate_limit_ms=self.settings.ocr.rate_limit_ms,
                cache_size=self.settings.ocr.cache_size,
            ),
            TemplateMatchProvider(),
        ]
        return TargetResolver(providers)

    def _build_browser_adapter(self) -> PlaywrightBrowserAdapter:
        return PlaywrightBrowserAdapter(
            cdp_url=self.settings.browser.cdp_url,
            launch_on_demand=self.settings.browser.launch_on_demand,
            channel=self.settings.browser.channel,
            headless=self.settings.browser.headless,
            default_timeout_ms=self.settings.browser.default_timeout_ms,
            connect_timeout_ms=self.settings.browser.connect_timeout_ms,
        )

    def _build_overlay(self, artifacts: ArtifactManager):
        if not self.settings.overlay.enabled:
            return NullOverlay()
        return TkDebugOverlay(
            artifacts=artifacts,
            enabled=True,
            duration_ms=self.settings.overlay.duration_ms,
            window_manager=self.window_manager,
        )

    def _load_hotkeys(self, hotkeys_path: str | Path) -> list[HotkeyBinding]:
        data = yaml.safe_load(Path(hotkeys_path).read_text(encoding="utf-8")) or {}
        return [HotkeyBinding(**raw) for raw in data.get("bindings", [])]

    def _track_token(self, token: EmergencyStopToken):
        application = self

        class _TokenContext:
            def __enter__(self_inner):
                with application._active_lock:
                    application._active_tokens.append(token)
                return token

            def __exit__(self_inner, exc_type, exc, tb):
                with application._active_lock:
                    if token in application._active_tokens:
                        application._active_tokens.remove(token)
                return False

        return _TokenContext()
