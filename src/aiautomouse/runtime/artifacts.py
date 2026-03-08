from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aiautomouse.runtime.fs import atomic_write_json


class ArtifactManager:
    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir = self.run_dir / "screenshots"
        self.overlay_dir = self.run_dir / "overlay"
        self.debug_dir = self.run_dir / "debug"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.overlay_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"

    def write_json(self, relative_path: str, payload: Any) -> Path:
        destination = self.run_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        return atomic_write_json(destination, payload)

    def capture_named_screenshot(self, name: str, screen_capture: object):
        slug = self._slug(name)
        destination = self.screenshots_dir / f"{slug}.png"
        try:
            image = screen_capture.capture()
            return screen_capture.save(image, destination)
        except Exception:
            return None

    def capture_failure_screenshot(self, step_id: str, screen_capture: object):
        return self.capture_named_screenshot(f"{step_id}_failure", screen_capture)

    def capture_step_screenshot(
        self,
        step_path: str,
        phase: str,
        screen_capture: object,
        *,
        window: object | None = None,
    ):
        slug = self._slug(step_path)
        destination = self.screenshots_dir / f"{slug}_{self._slug(phase)}.png"
        try:
            frame = screen_capture.capture_frame(window=window, reason=f"{slug}_{phase}") if window else screen_capture.capture_frame(reason=f"{slug}_{phase}")
            return screen_capture.save(frame.image, destination)
        except Exception:
            return None

    def save_overlay_snapshot(self, name: str, payload: dict[str, Any]) -> Path:
        destination = self.overlay_dir / f"{self._slug(name)}.json"
        return atomic_write_json(destination, payload)

    def write_step_snapshot(self, step_path: str, phase: str, payload: dict[str, Any]) -> Path:
        return self.write_json(f"debug/steps/{self._slug(step_path)}_{self._slug(phase)}.json", payload)

    def write_run_summary(self, payload: dict[str, Any]) -> Path:
        return self.write_json("summary.json", payload)

    def debug_path(self, *parts: str) -> Path:
        destination = self.debug_dir.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_") or "artifact"
