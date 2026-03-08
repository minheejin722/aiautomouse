from __future__ import annotations

import ctypes


def ensure_per_monitor_v2_dpi_awareness() -> str:
    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)
    mask = (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1
    per_monitor_v2 = ctypes.c_void_p((-4) & mask)

    try:
        if user32.SetProcessDpiAwarenessContext(per_monitor_v2):
            return "per-monitor-v2"
    except Exception:
        pass

    if shcore is not None:
        try:
            if shcore.SetProcessDpiAwareness(2) == 0:
                return "per-monitor"
        except Exception:
            pass

    try:
        if user32.SetProcessDPIAware():
            return "system-dpi-aware"
    except Exception:
        pass
    return "unmodified"

