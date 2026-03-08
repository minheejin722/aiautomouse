from __future__ import annotations

import json
from pathlib import Path

from aiautomouse.authoring.converter import NaturalLanguageMacroConverter
from aiautomouse.authoring.models import MacroAuthoringResult
from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.services.workspace import Workspace


class MacroAuthoringService:
    def __init__(self, settings_path: str | Path = "config/app.yaml") -> None:
        self.settings_path = Path(settings_path)
        self.settings = AppSettings.load(self.settings_path)
        self.workspace = Workspace(self.settings)
        self.converter = NaturalLanguageMacroConverter()

    def convert_text(
        self,
        text: str,
        *,
        macro_name: str | None = None,
        hotkey: str | None = None,
        target_profile: str = "default",
    ) -> MacroAuthoringResult:
        return self.converter.convert(
            text,
            existing_snippets={entry.name for entry in self.workspace.snippets.list_entries()},
            existing_templates={entry.name for entry in self.workspace.templates.list_entries()},
            macro_name=macro_name,
            hotkey=hotkey,
            target_profile=target_profile,
        )

    def write_macro_json(self, result: MacroAuthoringResult, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.macro_json, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
