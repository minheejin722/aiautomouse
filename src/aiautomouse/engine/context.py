from __future__ import annotations

import contextlib
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.models import PaddingSpec, RegionSpec, TargetSpec
from aiautomouse.engine.results import EmergencyStopError, Rect, TargetMatch

VARIABLE_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_.-]+)\}")


class RunMode(str, Enum):
    DRY_RUN = "dry-run"
    EXECUTE = "execute"


@dataclass
class RuntimeContext:
    settings: AppSettings
    mode: RunMode
    resolver: Any
    artifacts: Any
    event_logger: Any
    overlay: Any
    stop_token: Any
    input_controller: Any
    window_manager: Any
    screen_capture: Any
    snippets: Any
    templates: Any
    macro_path: Path
    macro: Any | None = None
    browser: Any | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: dict[str, Any] = field(default_factory=dict)
    references: dict[str, TargetMatch] = field(default_factory=dict)
    screenshots: list[str] = field(default_factory=list)
    clipboard_state: dict[str, Any] = field(default_factory=dict)
    active_window_info: dict[str, Any] = field(default_factory=dict)
    retry_counters: dict[str, int] = field(default_factory=dict)
    step_timings: dict[str, dict[str, Any]] = field(default_factory=dict)
    step_outcomes: dict[str, bool] = field(default_factory=dict)
    ocr_last_known_areas: dict[str, Rect] = field(default_factory=dict)
    ocr_debug_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    image_last_known_areas: dict[str, Rect] = field(default_factory=dict)
    image_debug_results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _variable_stack: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self._variable_stack:
            macro_vars = {}
            if self.macro is not None:
                macro_vars = dict(getattr(self.macro, "variables", {}) or {})
            self._variable_stack = [macro_vars]
        self.refresh_active_window()

    @property
    def is_dry_run(self) -> bool:
        return self.mode == RunMode.DRY_RUN

    def check_cancelled(self) -> None:
        if hasattr(self.stop_token, "is_set") and self.stop_token.is_set():
            raise EmergencyStopError("Emergency stop requested")

    def sleep(self, delay_ms: int) -> None:
        time.sleep(max(0, delay_ms) / 1000.0)

    def current_variables(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for scope in self._variable_stack:
            merged.update(scope)
        return merged

    def set_variable(self, name: str, value: Any) -> None:
        self._variable_stack[-1][name] = value

    @contextlib.contextmanager
    def push_variables(self, values: dict[str, Any] | None = None):
        scope = dict(values or {})
        self._variable_stack.append(scope)
        try:
            yield scope
        finally:
            self._variable_stack.pop()

    def render_string(self, text: str) -> str:
        variables = self.current_variables()

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(variables.get(key, match.group(0)))

        return VARIABLE_PATTERN.sub(replace, text)

    def render_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.render_string(value)
        if isinstance(value, list):
            return [self.render_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.render_value(item) for item in value)
        if isinstance(value, dict):
            return {key: self.render_value(item) for key, item in value.items()}
        return value

    def resolve_int(self, value: int | str) -> int:
        if isinstance(value, int):
            return value
        return int(self.render_string(str(value)))

    def remember_ref(self, name: str, match: TargetMatch) -> None:
        self.references[name] = match
        self.state.setdefault("found_regions", {})[name] = match.to_dict()

    def get_ref(self, name: str) -> TargetMatch:
        return self.references[name]

    def remember_screenshot(self, path: str | None) -> None:
        if path:
            self.screenshots.append(path)
            self.state["screenshots"] = list(self.screenshots)

    def remember_clipboard(self, before: str | None = None, after: str | None = None) -> None:
        if before is not None:
            self.clipboard_state["before"] = before
        if after is not None:
            self.clipboard_state["after"] = after
        self.state["clipboard_state"] = dict(self.clipboard_state)

    def refresh_active_window(self) -> dict[str, Any]:
        info = self.window_manager.get_active_window_info()
        self.active_window_info = info
        self.state["active_window"] = dict(info)
        return info

    def mark_retry_attempt(self, step_path: str, attempt: int) -> None:
        self.retry_counters[step_path] = attempt
        self.state["retry_counters"] = dict(self.retry_counters)

    def mark_step_started(self, step_path: str) -> float:
        started_at = time.perf_counter()
        self.step_timings[step_path] = {"started_at": started_at}
        return started_at

    def mark_step_finished(self, step_path: str, started_at: float, status: str) -> int:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        self.step_timings.setdefault(step_path, {})
        self.step_timings[step_path]["duration_ms"] = duration_ms
        self.step_timings[step_path]["status"] = status
        self.state["step_timing"] = dict(self.step_timings)
        return duration_ms

    def register_step_outcome(self, step_id: str, success: bool) -> None:
        self.step_outcomes[step_id] = success
        self.state["step_outcomes"] = dict(self.step_outcomes)

    def remember_last_known_area(self, key: str, rect: Rect) -> None:
        self.ocr_last_known_areas[key] = rect
        self.state.setdefault("ocr_last_known_areas", {})
        self.state["ocr_last_known_areas"][key] = rect.to_dict()

    def get_last_known_area(self, key: str) -> Rect | None:
        return self.ocr_last_known_areas.get(key)

    def remember_ocr_results(self, key: str, results: list[dict[str, Any]]) -> None:
        self.ocr_debug_results[key] = results
        self.state.setdefault("ocr_debug_results", {})
        self.state["ocr_debug_results"][key] = list(results)

    def remember_image_last_known_area(self, key: str, rect: Rect) -> None:
        self.image_last_known_areas[key] = rect
        self.state.setdefault("image_last_known_areas", {})
        self.state["image_last_known_areas"][key] = rect.to_dict()

    def get_image_last_known_area(self, key: str) -> Rect | None:
        return self.image_last_known_areas.get(key)

    def remember_image_results(self, key: str, results: list[dict[str, Any]]) -> None:
        self.image_debug_results[key] = results
        self.state.setdefault("image_debug_results", {})
        self.state["image_debug_results"][key] = list(results)

    def resolve_target(self, target: TargetSpec | None) -> TargetSpec | None:
        if target is None:
            return None
        payload: dict[str, Any] = {}
        if target.anchor:
            if self.macro is None or target.anchor not in self.macro.anchors:
                raise KeyError(f"Unknown anchor: {target.anchor}")
            payload = self.macro.anchors[target.anchor].model_dump(exclude_none=True, mode="python")
        override = target.model_dump(exclude_none=True, mode="python")
        override.pop("anchor", None)
        payload = _deep_merge(payload, override)
        payload = self.render_value(payload)
        if "region" in payload:
            resolved_region = self.resolve_region(payload["region"])
            if resolved_region is not None:
                payload["region"] = resolved_region
        return TargetSpec.model_validate(payload)

    def resolve_region(self, region: Any) -> dict[str, int] | None:
        if region is None:
            return None
        if isinstance(region, str):
            if self.macro is not None and region in getattr(self.macro, "regions", {}):
                return self.resolve_region(self.macro.regions[region])
            if region in self.references:
                return self.references[region].rect.to_dict()
            raise KeyError(f"Unknown region reference: {region}")
        if isinstance(region, RegionSpec):
            base_rect = self._region_base_rect(region)
            return self._apply_padding(base_rect, region.padding).to_dict()
        if isinstance(region, dict):
            return self.resolve_region(RegionSpec.model_validate(region))
        if isinstance(region, Rect):
            return region.to_dict()
        raise ValueError(f"Unsupported region payload: {region!r}")

    def _region_base_rect(self, region: RegionSpec) -> Rect:
        if region.region_ref:
            resolved = self.resolve_region(region.region_ref)
            return Rect(**resolved)
        if region.ref:
            return self.get_ref(region.ref).rect
        return Rect(
            left=self.resolve_int(region.left),
            top=self.resolve_int(region.top),
            width=self.resolve_int(region.width),
            height=self.resolve_int(region.height),
        )

    def _apply_padding(self, rect: Rect, padding: int | PaddingSpec | None) -> Rect:
        if padding is None:
            return rect
        if isinstance(padding, int):
            pad = PaddingSpec(left=padding, top=padding, right=padding, bottom=padding)
        else:
            pad = padding
        return Rect(
            left=rect.left - pad.left,
            top=rect.top - pad.top,
            width=rect.width + pad.left + pad.right,
            height=rect.height + pad.top + pad.bottom,
        )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
