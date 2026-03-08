from __future__ import annotations

from pathlib import Path

import pytest

from aiautomouse.app import AutomationApplication
from aiautomouse.providers.windows_uia import WindowsUiaProvider
from tests.conftest import require_desktop_integration, terminate_process

pytestmark = pytest.mark.integration


def test_calculator_macro_executes_successfully():
    require_desktop_integration()
    if not WindowsUiaProvider().is_available():
        pytest.skip("uiautomation is not available")
    app = AutomationApplication()
    try:
        result = app.run_macro(Path("macros/samples/calculator_click_button.yaml"), mode="execute")
        assert result.status.value == "success"
    finally:
        terminate_process("CalculatorApp.exe")
        terminate_process("calc.exe")

