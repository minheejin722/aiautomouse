from __future__ import annotations

import os
import subprocess

import pytest


def require_desktop_integration() -> None:
    if os.name != "nt":
        pytest.skip("Windows-only desktop integration test")
    if os.getenv("AIAUTOMOUSE_RUN_INTEGRATION") != "1":
        pytest.skip("Set AIAUTOMOUSE_RUN_INTEGRATION=1 to run desktop integration tests")


def terminate_process(image_name: str) -> None:
    subprocess.run(
        ["taskkill", "/IM", image_name, "/F"],
        check=False,
        capture_output=True,
        text=True,
    )

