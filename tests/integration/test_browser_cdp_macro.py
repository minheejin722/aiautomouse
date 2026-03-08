from __future__ import annotations

import json

import pytest

from aiautomouse.app import AutomationApplication
from aiautomouse.providers.browser_cdp import BrowserCdpProvider
from tests.conftest import require_desktop_integration

pytestmark = pytest.mark.integration


def test_browser_cdp_macro_executes_when_browser_is_available():
    require_desktop_integration()
    app = AutomationApplication()
    provider = BrowserCdpProvider(app._build_browser_adapter())
    if not provider.is_available():
        pytest.skip("Chromium CDP endpoint is unavailable")
    macro_path = app.settings.paths.macros_dir / "_browser_adapter_integration.json"
    macro_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "name": "browser_adapter_integration",
                "steps": [
                    {
                        "type": "open_page",
                        "url": "data:text/html,<html><body><input aria-label='Search'/><button>Upload</button></body></html>",
                        "new_window": True,
                    },
                    {
                        "type": "click",
                        "target": {
                            "dom": {
                                "label": "Search",
                                "wait_for": "visible",
                                "require_enabled": True,
                                "require_stable": True,
                            }
                        },
                    },
                    {"type": "type_text", "text": "desktop automation"},
                    {
                        "type": "find_text",
                        "query": "Upload",
                        "strategy": "dom",
                        "save_as": "upload_btn",
                    },
                    {"type": "click_ref", "ref": "upload_btn"},
                    {"type": "verify_text", "query": "Upload", "strategy": "dom"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = app.run_macro(macro_path, mode="execute")
    assert result.status.value == "success"
