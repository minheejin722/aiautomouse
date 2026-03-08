from __future__ import annotations

from pathlib import Path

from aiautomouse.app import AutomationApplication
from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.loader import load_macro
from aiautomouse.engine.schema import write_macro_json_schema
from aiautomouse.platform.win32_hotkeys import HotkeyBinding
from aiautomouse.services.authoring import MacroAuthoringService
from aiautomouse.services.hotkeys import HotkeyServiceController
from aiautomouse.services.workspace import Workspace


class DesktopAutomationService:
    def __init__(self, settings_path: str | Path = "config/app.yaml") -> None:
        self.settings_path = Path(settings_path)
        self.automation_app = AutomationApplication(self.settings_path)
        self.settings = self.automation_app.settings
        self.workspace = Workspace(self.settings)
        self.authoring = MacroAuthoringService(self.settings_path)
        self.hotkeys = HotkeyServiceController(self.automation_app, self.workspace.hotkeys)
        write_macro_json_schema(self.settings.paths.schema_path)

    def save_settings(self, settings: AppSettings) -> Path:
        settings.ensure_directories()
        saved = settings.save(self.settings_path)
        self.settings = AppSettings.load(self.settings_path)
        self.automation_app = AutomationApplication(self.settings_path)
        self.workspace = Workspace(self.settings)
        self.authoring = MacroAuthoringService(self.settings_path)
        self.hotkeys = HotkeyServiceController(self.automation_app, self.workspace.hotkeys)
        write_macro_json_schema(self.settings.paths.schema_path)
        return saved

    def run_macro(self, macro_path: str | Path, mode: str):
        return self.automation_app.run_macro(macro_path, mode=mode)

    def register_hotkey(self, macro_path: str | Path, hotkey: str, mode: str = "execute") -> Path:
        binding = HotkeyBinding(hotkey=hotkey, macro=str(Path(macro_path).resolve()), mode=mode)
        saved = self.workspace.hotkeys.upsert_binding(binding)
        if self.hotkeys.is_running():
            self.hotkeys.reload()
        return saved

    def unregister_hotkey(self, macro_path: str | Path) -> Path:
        saved = self.workspace.hotkeys.remove_binding_for_macro(macro_path)
        if self.hotkeys.is_running():
            self.hotkeys.reload()
        return saved

    def get_macro_hotkey(self, macro_path: str | Path) -> HotkeyBinding | None:
        resolved = Path(macro_path).resolve()
        for binding in self.workspace.hotkeys.load_bindings():
            if Path(binding.macro).resolve() == resolved:
                return binding
        return None

    def validate_macro_file(self, path: str | Path):
        return load_macro(path)

    def shutdown(self) -> None:
        if self.hotkeys.is_running():
            self.hotkeys.stop()
        self.automation_app.shutdown()
