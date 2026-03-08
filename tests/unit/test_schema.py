from __future__ import annotations

from aiautomouse.engine.schema import get_macro_json_schema


def test_macro_json_schema_contains_version_and_step_defs():
    schema = get_macro_json_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "AIAutoMouse Macro v2.0" in schema["title"]
    assert "$defs" in schema
    assert "FocusWindowStep" in schema["$defs"]
    assert "FindTextStep" in schema["$defs"]

