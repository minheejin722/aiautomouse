from __future__ import annotations

from unittest.mock import MagicMock, patch

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.services.authoring import MacroAuthoringService
from aiautomouse.services.hotkeys import HotkeyServiceController
from aiautomouse.services.workspace import Workspace


def test_save_settings_preserves_instance_identity(tmp_path):
    """After save_settings(), internal service instances must NOT be replaced.

    This is the core assertion for the M-6 fix: the same AutomationApplication,
    Workspace, MacroAuthoringService, and HotkeyServiceController objects continue
    to be used, preventing orphan state during macro execution.
    """
    settings_path = tmp_path / "config" / "app.yaml"
    settings = AppSettings.from_dict(
        {
            "paths": {
                "snippets_dir": str(tmp_path / "snippets"),
                "templates_dir": str(tmp_path / "templates"),
                "macros_dir": str(tmp_path / "macros"),
                "hotkeys_path": str(tmp_path / "config" / "hotkeys.yaml"),
                "logs_dir": str(tmp_path / "logs"),
                "artifacts_dir": str(tmp_path / "logs" / "runs"),
                "schema_path": str(tmp_path / "schemas" / "macro.schema.json"),
            },
        }
    )
    settings.save(settings_path)

    # Build a DesktopAutomationService-like structure without heavy platform deps
    # by mocking AutomationApplication
    with patch("aiautomouse.services.desktop.AutomationApplication") as MockApp:
        mock_app = MagicMock()
        mock_app.settings = settings
        mock_app.settings_path = settings_path
        MockApp.return_value = mock_app

        from aiautomouse.services.desktop import DesktopAutomationService

        with patch("aiautomouse.services.desktop.write_macro_json_schema"):
            service = DesktopAutomationService(settings_path)

        # Record original object identities
        original_app_id = id(service.automation_app)
        original_workspace_id = id(service.workspace)
        original_authoring_id = id(service.authoring)
        original_hotkeys_id = id(service.hotkeys)

        # Prepare modified settings with a changed log level
        modified = AppSettings.from_dict(
            {
                **settings.model_dump(mode="python"),
                "log_level": "DEBUG",
            }
        )

        # Mock update_settings on the app to actually reload settings like the real one
        def fake_update(path=None):
            mock_app.settings = AppSettings.load(settings_path)

        mock_app.update_settings.side_effect = fake_update

        with patch("aiautomouse.services.desktop.write_macro_json_schema"):
            service.save_settings(modified)

        # ── Identity assertions ──
        assert id(service.automation_app) == original_app_id, "AutomationApplication was replaced!"
        assert id(service.workspace) == original_workspace_id, "Workspace was replaced!"
        assert id(service.authoring) == original_authoring_id, "MacroAuthoringService was replaced!"
        assert id(service.hotkeys) == original_hotkeys_id, "HotkeyServiceController was replaced!"

        # Verify update_settings was called (not constructor)
        mock_app.update_settings.assert_called_once()
