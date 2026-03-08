from __future__ import annotations

from pathlib import Path

import pytest

from aiautomouse.app import AutomationApplication
from aiautomouse.providers.windows_uia import WindowsUiaProvider
from tests.conftest import require_desktop_integration, terminate_process

pytestmark = pytest.mark.integration


def test_notepad_macro_executes_successfully():
    require_desktop_integration()
    if not WindowsUiaProvider().is_available():
        pytest.skip("uiautomation is not available")
    app = AutomationApplication()
    try:
        result = app.run_macro(Path("macros/samples/notepad_insert_snippet.yaml"), mode="execute")
        assert result.status.value == "success"
    finally:
        terminate_process("notepad.exe")

