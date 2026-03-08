from __future__ import annotations

import json
from pathlib import Path

from aiautomouse.engine.models import CURRENT_SCHEMA_VERSION, MacroSpec

MACRO_SCHEMA_ID = "https://schemas.aiautomouse.local/macro.schema.json"


def get_macro_json_schema() -> dict:
    schema = MacroSpec.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = MACRO_SCHEMA_ID
    schema["title"] = f"AIAutoMouse Macro v{CURRENT_SCHEMA_VERSION}"
    return schema


def write_macro_json_schema(path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(get_macro_json_schema(), indent=2), encoding="utf-8")
    return destination
