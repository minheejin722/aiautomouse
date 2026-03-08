from __future__ import annotations

import json

from aiautomouse.engine.loader import load_macro


def test_loads_current_schema_macro_with_hotkey_and_target_profile(tmp_path):
    macro_path = tmp_path / "macro.json"
    macro_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "name": "upload_and_submit",
                "hotkey": "ctrl+alt+1",
                "target_profile": "default",
                "variables": {"button_text": "업로드"},
                "steps": [
                    {"type": "focus_window", "title_contains": "Chrome"},
                    {
                        "type": "find_text",
                        "query": "${button_text}",
                        "strategy": "uia_or_ocr",
                        "save_as": "upload_btn",
                    },
                    {"type": "click_ref", "ref": "upload_btn"},
                ],
            }
        ),
        encoding="utf-8",
    )

    macro = load_macro(macro_path)

    assert macro.schema_version == "2.0"
    assert macro.hotkey == "ctrl+alt+1"
    assert macro.target_profile == "default"
    assert macro.steps[0].type == "focus_window"
    assert macro.steps[1].save_as == "upload_btn"


def test_legacy_macro_is_migrated_to_legacy_compat_step(tmp_path):
    macro_path = tmp_path / "legacy.yaml"
    macro_path.write_text(
        """
name: legacy_macro
steps:
  - id: one
    name: One
    precondition:
      kind: always
    action:
      kind: noop
    postcondition:
      kind: always
    rollback:
      kind: noop
    fallback:
      kind: noop
""".strip(),
        encoding="utf-8",
    )

    macro = load_macro(macro_path)

    assert macro.schema_version == "2.0"
    assert macro.steps[0].type == "legacy_compat"
    assert macro.steps[0].legacy.action.kind == "noop"

