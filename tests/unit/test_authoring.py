from __future__ import annotations

import json

from aiautomouse.authoring.converter import NaturalLanguageMacroConverter
from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.cli import main


SAMPLE_PROMPT = (
    "\ucc3d \uc81c\ubaa9\uc5d0 Chrome\uc774 \ud3ec\ud568\ub41c \ucc3d\uc744 \ud65c\uc131\ud654\ud558\uace0, "
    "\ud654\uba74\uc5d0\uc11c '\uc5c5\ub85c\ub4dc' \ud14d\uc2a4\ud2b8\ub97c \ucc3e\uace0 \ud074\ub9ad\ud55c \ub4a4, "
    "snippet prompt_01\uc744 \ubd99\uc5ec\ub123\uace0 Enter\ub97c \ub20c\ub7ec."
)


def test_converter_builds_validated_macro_json_with_browser_recommendation():
    result = NaturalLanguageMacroConverter().convert(
        SAMPLE_PROMPT,
        existing_snippets={"hello"},
        existing_templates={"calc_equals"},
    )

    steps = result.macro_json["steps"]

    assert [step["type"] for step in steps] == [
        "focus_window",
        "find_text",
        "click_ref",
        "paste_snippet",
        "press_keys",
    ]
    assert steps[0]["title_contains"] == "Chrome"
    assert steps[1]["query"] == "\uc5c5\ub85c\ub4dc"
    assert steps[1]["strategy"] == "dom_or_uia_or_ocr"
    assert steps[2]["ref"] == steps[1]["save_as"]
    assert steps[3]["snippet_id"] == "prompt_01"
    assert steps[4]["keys"] == "enter"
    assert result.target_adapter_recommendation.adapter == "browser"
    assert any("ambiguous" in warning.message.lower() for warning in result.ambiguous_step_warnings)
    assert result.required_resources_checklist[0].resource_id == "prompt_01"
    assert result.required_resources_checklist[0].exists is False


def test_converter_recommends_image_adapter_for_template_prompt():
    prompt = "template done_icon\uc744 \ucc3e\uace0 \ud074\ub9ad\ud574."

    result = NaturalLanguageMacroConverter().convert(
        prompt,
        existing_snippets=set(),
        existing_templates={"done_icon"},
    )

    assert result.macro_json["steps"][0]["type"] == "find_image"
    assert result.macro_json["steps"][0]["template_id"] == "done_icon"
    assert result.macro_json["steps"][1]["type"] == "click_ref"
    assert result.target_adapter_recommendation.adapter == "image"
    assert result.required_resources_checklist[0].exists is True


def test_cli_author_command_prints_report_and_writes_macro_json(tmp_path, capsys):
    settings_path = tmp_path / "app.yaml"
    snippets_dir = tmp_path / "snippets"
    templates_dir = tmp_path / "templates"
    macros_dir = tmp_path / "macros"
    prompt_path = tmp_path / "prompt.txt"
    output_path = tmp_path / "generated.json"

    settings = AppSettings.from_dict(
        {
            "paths": {
                "snippets_dir": str(snippets_dir),
                "templates_dir": str(templates_dir),
                "macros_dir": str(macros_dir),
                "hotkeys_path": str(tmp_path / "hotkeys.yaml"),
                "artifacts_dir": str(tmp_path / "artifacts"),
                "schema_path": str(tmp_path / "schema.json"),
            }
        }
    )
    settings.save(settings_path)
    snippets_dir.mkdir(parents=True, exist_ok=True)
    (snippets_dir / "prompt_01.txt").write_text("hello", encoding="utf-8")
    prompt_path.write_text(SAMPLE_PROMPT, encoding="utf-8")

    exit_code = main(
        [
            "--settings",
            str(settings_path),
            "author",
            "--input-file",
            str(prompt_path),
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.out)
    written_macro = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["required_resources_checklist"][0]["exists"] is True
    assert report["target_adapter_recommendation"]["adapter"] == "browser"
    assert written_macro["steps"][3]["type"] == "paste_snippet"
    assert written_macro["steps"][3]["snippet_id"] == "prompt_01"
