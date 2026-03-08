from __future__ import annotations

import os
import queue
import threading
import time

from aiautomouse.engine.results import TargetMatch
from aiautomouse.providers.ocr_common import OcrTextResult


class NullOverlay:
    def show_target(self, match: TargetMatch, label: str = "", status: str = "planned") -> None:
        return None

    def show_ocr_results(self, results: list[OcrTextResult], label: str = "", status: str = "recognized") -> None:
        return None

    def close(self) -> None:
        return None


class TkDebugOverlay:
    def __init__(self, artifacts, enabled: bool = True, duration_ms: int = 900, window_manager=None) -> None:
        self.artifacts = artifacts
        self.enabled = enabled
        self.duration_ms = duration_ms
        self.window_manager = window_manager
        self.live_enabled = enabled and os.getenv("AIAUTOMOUSE_LIVE_OVERLAY") == "1"
        self._queue: queue.Queue[dict] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._counter = 0
        if self.live_enabled:
            try:
                import tkinter  # noqa: F401
            except Exception:
                self.live_enabled = False
            else:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def show_target(self, match: TargetMatch, label: str = "", status: str = "planned") -> None:
        self._counter += 1
        payload = {
            "kind": "target",
            "label": label,
            "status": status,
            "match": match.to_dict(),
            "index": self._counter,
            "created_at": time.time(),
        }
        self.artifacts.save_overlay_snapshot(f"{self._counter:03d}_{label or status}", payload)
        if self.live_enabled:
            self._queue.put(payload)

    def show_ocr_results(self, results: list[OcrTextResult], label: str = "", status: str = "recognized") -> None:
        if not results:
            return
        self._counter += 1
        payload = {
            "kind": "ocr_results",
            "label": label,
            "status": status,
            "results": [result.to_dict() for result in results],
            "index": self._counter,
            "created_at": time.time(),
        }
        self.artifacts.save_overlay_snapshot(f"{self._counter:03d}_{label or status}", payload)
        if self.live_enabled:
            self._queue.put(payload)

    def close(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:  # pragma: no cover - GUI behavior
        import tkinter as tk

        window = tk.Tk()
        screen = self.window_manager.get_virtual_screen()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.geometry(f"{screen.width}x{screen.height}+{screen.left}+{screen.top}")
        window.configure(bg="white")
        try:
            window.attributes("-transparentcolor", "white")
        except tk.TclError:
            window.attributes("-alpha", 0.25)
        canvas = tk.Canvas(window, bg="white", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        def clear() -> None:
            canvas.delete("all")

        def draw(payload: dict) -> None:
            clear()
            if payload.get("kind") == "ocr_results":
                for item in payload.get("results", [])[:20]:
                    rect = item["bbox"]
                    offset_x = rect["left"] - screen.left
                    offset_y = rect["top"] - screen.top
                    x2 = offset_x + rect["width"]
                    y2 = offset_y + rect["height"]
                    canvas.create_rectangle(offset_x, offset_y, x2, y2, outline="orange", width=2)
                    canvas.create_text(
                        offset_x + 4,
                        max(12, offset_y - 8),
                        anchor="sw",
                        fill="orange",
                        text=item["text"],
                        font=("Segoe UI", 9, "bold"),
                    )
            else:
                rect = payload["match"]["rect"]
                offset_x = rect["left"] - screen.left
                offset_y = rect["top"] - screen.top
                x2 = offset_x + rect["width"]
                y2 = offset_y + rect["height"]
                canvas.create_rectangle(offset_x, offset_y, x2, y2, outline="red", width=3)
                center_x = offset_x + rect["width"] / 2
                center_y = offset_y + rect["height"] / 2
                canvas.create_oval(center_x - 6, center_y - 6, center_x + 6, center_y + 6, outline="red", width=2)
                canvas.create_text(
                    offset_x + 8,
                    max(12, offset_y - 8),
                    anchor="sw",
                    fill="red",
                    text=f"{payload['label']} [{payload['status']}] {payload['match']['provider_name']}",
                    font=("Segoe UI", 10, "bold"),
                )
            window.after(self.duration_ms, clear)

        def pump() -> None:
            if self._stop.is_set():
                window.destroy()
                return
            try:
                payload = self._queue.get_nowait()
            except queue.Empty:
                pass
            else:
                draw(payload)
            window.after(50, pump)

        window.after(0, pump)
        window.mainloop()
