from __future__ import annotations

import json

from aiautomouse.bootstrap.settings import AppSettings


def test_app_settings_save_and_load_json(tmp_path):
    settings_path = tmp_path / "config" / "app.json"
    settings = AppSettings.from_dict(
        {
            "emergency_stop_hotkey": "Ctrl+Alt+End",
            "paths": {
                "logs_dir": str(tmp_path / "portable-logs"),
                "artifacts_dir": str(tmp_path / "portable-logs" / "runs"),
            },
            "diagnostics": {
                "capture_before_after_screenshots": True,
                "replay_log_enabled": True,
            },
        }
    )

    saved_path = settings.save(settings_path)
    reloaded = AppSettings.load(saved_path)
    raw = json.loads(settings_path.read_text(encoding="utf-8"))

    assert saved_path == settings_path
    assert raw["emergency_stop_hotkey"] == "Ctrl+Alt+End"
    assert raw["paths"]["logs_dir"].endswith("portable-logs")
    assert reloaded.emergency_stop_hotkey == "Ctrl+Alt+End"
    assert reloaded.paths.logs_dir.name == "portable-logs"
    assert reloaded.paths.artifacts_dir.name == "runs"


def test_app_settings_load_creates_missing_file(tmp_path):
    settings_path = tmp_path / "config" / "generated.json"

    loaded = AppSettings.load(settings_path)

    assert settings_path.exists()
    assert loaded.paths.logs_dir.exists()
    assert loaded.paths.artifacts_dir.exists()
