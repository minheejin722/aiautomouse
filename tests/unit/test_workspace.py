from __future__ import annotations

import json
from pathlib import Path

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.platform.win32_hotkeys import HotkeyBinding
from aiautomouse.services.workspace import Workspace


def test_workspace_repositories_crud(tmp_path):
    settings = AppSettings.from_dict(
        {
            "paths": {
                "snippets_dir": str(tmp_path / "snippets"),
                "templates_dir": str(tmp_path / "templates"),
                "macros_dir": str(tmp_path / "macros"),
                "hotkeys_path": str(tmp_path / "config" / "hotkeys.yaml"),
                "artifacts_dir": str(tmp_path / "artifacts"),
                "schema_path": str(tmp_path / "schemas" / "macro.schema.json"),
            }
        }
    )
    workspace = Workspace(settings)

    workspace.snippets.save("alpha", "hello")
    assert workspace.snippets.read("alpha") == "hello"

    macro_path = workspace.macros.save_text(
        "sample",
        json.dumps({"schema_version": "2.0", "name": "sample", "steps": [{"type": "verify_all", "conditions": [{"type": "always"}]}]}),
        extension=".json",
    )
    validated = workspace.macros.validate_text(workspace.macros.read_text(macro_path), ".json")
    assert validated["name"] == "sample"

    template_path = workspace.templates.save_bytes("template", b"PNGDATA", suffix=".bin")
    assert template_path.exists()

    workspace.hotkeys.save_bindings([HotkeyBinding(hotkey="Ctrl+Alt+1", macro=str(macro_path), mode="dry-run")])
    assert workspace.hotkeys.load_bindings()[0].hotkey == "Ctrl+Alt+1"


def test_run_history_reads_saved_run_metadata(tmp_path):
    settings = AppSettings.from_dict(
        {
            "paths": {
                "snippets_dir": str(tmp_path / "snippets"),
                "templates_dir": str(tmp_path / "templates"),
                "macros_dir": str(tmp_path / "macros"),
                "hotkeys_path": str(tmp_path / "config" / "hotkeys.yaml"),
                "artifacts_dir": str(tmp_path / "artifacts"),
                "schema_path": str(tmp_path / "schemas" / "macro.schema.json"),
            }
        }
    )
    workspace = Workspace(settings)
    run_dir = settings.paths.artifacts_dir / "run123"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    (run_dir / "screenshots" / "fail.png").write_bytes(b"png")
    (run_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "macro_started", "macro": "demo", "mode": "dry-run", "timestamp": "2026-03-08T00:00:00Z"}),
                json.dumps({"event": "macro_finished", "status": "failed", "timestamp": "2026-03-08T00:00:01Z", "failed_step_id": "find_upload"}),
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps({"failed_step_id": "find_upload", "error": "window not found"}),
        encoding="utf-8",
    )

    runs = workspace.runs.list_runs()

    assert len(runs) == 1
    assert runs[0].macro_name == "demo"
    assert runs[0].status == "failed"
    assert runs[0].failed_step_id == "find_upload"
    assert runs[0].error == "window not found"
    assert runs[0].screenshots[0].name == "fail.png"
