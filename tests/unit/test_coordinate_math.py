from __future__ import annotations

from aiautomouse.platform import win32_windows


def test_physical_to_absolute_supports_negative_virtual_origins(monkeypatch):
    monkeypatch.setattr(
        win32_windows,
        "get_virtual_screen",
        lambda: win32_windows.VirtualScreen(left=-1920, top=0, width=3840, height=1080),
    )

    assert win32_windows.physical_to_absolute(-1920, 0) == (0, 0)
    assert win32_windows.physical_to_absolute(1919, 1079) == (65535, 65535)

