from __future__ import annotations

from pathlib import Path

import pytest

from aiautomouse.app import AutomationApplication
from aiautomouse.providers.windows_ocr import WindowsOcrProvider
from tests.conftest import require_desktop_integration

pytestmark = pytest.mark.integration


def test_ocr_macro_executes_when_windows_ocr_is_available():
    require_desktop_integration()
    if not WindowsOcrProvider().is_available():
        pytest.skip("Windows OCR is unavailable")
    app = AutomationApplication()
    result = app.run_macro(Path("macros/samples/screen_find_text_ocr.yaml"), mode="dry-run")
    assert result.status.value == "success"

