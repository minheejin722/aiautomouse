from __future__ import annotations

import contextlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiautomouse.engine.models import TargetSpec, TemplateLocatorSpec
from aiautomouse.engine.results import Rect, TargetMatch
from aiautomouse.providers.base import LocatorProvider
from aiautomouse.providers.image_match_common import (
    SearchPlanEntry,
    TemplateMatchCandidate,
    build_scale_candidates,
    filter_duplicate_candidates,
    frame_difference_score,
    non_max_suppression,
)
from aiautomouse.providers.ocr_common import OcrResultCache
from aiautomouse.resources.templates import TemplateAsset


@dataclass(frozen=True)
class EffectiveTemplateSpec:
    reference: str
    path: Path
    threshold: float
    preferred_theme: str | None
    preferred_dpi: int | None
    language_hint: str | None
    search_region_hint: Any
    click_offset: dict[str, int]
    use_grayscale: bool
    use_mask: bool
    mask_path: Path | None
    multi_scale: bool
    scales: list[float]
    top_n: int
    monitor_index: int | None
    last_known_padding: int
    notes: str
    name: str | None


@dataclass
class FrameSearchState:
    frame_array: Any
    match: TargetMatch | None
    candidates: list[dict[str, Any]]
    reason: str | None


class TemplateMatchProvider(LocatorProvider):
    name = "template_match"
    supported_fields = ("template",)

    def __init__(
        self,
        *,
        cache_size: int = 128,
        diff_threshold: float = 0.01,
        nms_iou_threshold: float = 0.35,
    ) -> None:
        self.diff_threshold = max(0.0, float(diff_threshold))
        self.nms_iou_threshold = max(0.0, float(nms_iou_threshold))
        self.selection_cache = OcrResultCache(cache_size)
        self.frame_history: dict[str, FrameSearchState] = {}

    def is_available(self) -> bool:
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                import cv2  # noqa: F401
                import numpy  # noqa: F401
        except Exception:
            return False
        return True

    def find(self, target: TargetSpec, ctx: object):
        template_spec = target.template
        if template_spec is None:
            return None
        reference = template_spec.path or template_spec.template_id
        if not reference:
            return None
        template_asset = ctx.templates.get(reference)
        if not template_asset.path.exists():
            self._emit_failure(ctx, template_asset.reference, "template_path_missing", {"template_path": str(template_asset.path)})
            return None
        effective = self._merge_template_spec(template_asset, template_spec, target)
        query_key = self._query_key(effective, target)
        search_plan = self._build_search_plan(target, effective, ctx, query_key)
        failure_reasons: list[dict[str, Any]] = []
        for plan in search_plan:
            frame = ctx.screen_capture.capture_frame(region=plan.rect.to_dict(), reason="template_search")
            state_key = f"{query_key}:{plan.label}"
            frame_array = self._frame_bgr_array(frame)
            cached_state = self.frame_history.get(state_key)
            if cached_state is not None:
                diff = frame_difference_score(cached_state.frame_array, frame_array)
                if diff <= self.diff_threshold:
                    self._emit_debug_event(
                        ctx,
                        "template_match_frame_reused",
                        template=effective.reference,
                        search_label=plan.label,
                        diff_score=diff,
                        had_match=bool(cached_state.match),
                    )
                    if cached_state.match is not None:
                        return cached_state.match
                    continue
            candidates, debug_payload = self._search_frame(frame_array, frame.rect, plan, effective, ctx)
            self._save_debug_artifacts(ctx, effective, frame, plan, debug_payload)
            if hasattr(ctx, "remember_image_results"):
                ctx.remember_image_results(
                    f"{query_key}:{plan.label}",
                    [candidate.to_dict() for candidate in candidates],
                )
            if not candidates:
                failure_reasons.append(
                    {
                        "search_label": plan.label,
                        "reason": debug_payload["failure_reason"],
                    }
                )
                self.frame_history[state_key] = FrameSearchState(
                    frame_array=frame_array,
                    match=None,
                    candidates=[],
                    reason=debug_payload["failure_reason"],
                )
                continue
            chosen = candidates[0]
            match = TargetMatch(
                provider_name=self.name,
                rect=chosen.bbox,
                confidence=float(chosen.score),
                metadata={
                    "template_reference": effective.reference,
                    "template_path": str(effective.path),
                    "preferred_theme": effective.preferred_theme,
                    "preferred_dpi": effective.preferred_dpi,
                    "language_hint": effective.language_hint,
                    "click_offset": dict(effective.click_offset),
                    "top_candidates": [candidate.to_dict() for candidate in candidates[: effective.top_n]],
                    "chosen_candidate": chosen.to_dict(),
                    "heatmap_path": debug_payload.get("heatmap_path"),
                    "failure_reason": None,
                },
            )
            if hasattr(ctx, "remember_image_last_known_area"):
                ctx.remember_image_last_known_area(query_key, chosen.bbox)
            self.frame_history[state_key] = FrameSearchState(
                frame_array=frame_array,
                match=match,
                candidates=[candidate.to_dict() for candidate in candidates],
                reason=None,
            )
            self._emit_debug_event(
                ctx,
                "template_match_selected",
                template=effective.reference,
                search_label=plan.label,
                score=chosen.score,
                bbox=chosen.bbox.to_dict(),
            )
            return match
        self._emit_failure(
            ctx,
            effective.reference,
            "template_search_exhausted",
            {"reasons": failure_reasons},
        )
        return None

    def _merge_template_spec(
        self,
        asset: TemplateAsset,
        locator: TemplateLocatorSpec,
        target: TargetSpec,
    ) -> EffectiveTemplateSpec:
        metadata = asset.metadata
        click_offset = locator.click_offset if locator.click_offset is not None else metadata.click_offset
        return EffectiveTemplateSpec(
            reference=asset.reference,
            path=asset.path,
            threshold=float(locator.confidence or metadata.threshold or target.confidence),
            preferred_theme=locator.preferred_theme or metadata.preferred_theme,
            preferred_dpi=locator.preferred_dpi or metadata.preferred_dpi,
            language_hint=metadata.language_hint,
            search_region_hint=locator.search_region_hint if locator.search_region_hint is not None else metadata.search_region_hint,
            click_offset=self._offset_dict(click_offset),
            use_grayscale=locator.use_grayscale if locator.use_grayscale is not None else metadata.use_grayscale,
            use_mask=locator.use_mask if locator.use_mask is not None else metadata.use_mask,
            mask_path=asset.mask_path,
            multi_scale=locator.multi_scale if locator.multi_scale is not None else metadata.multi_scale,
            scales=locator.scales or metadata.scales,
            top_n=max(1, locator.top_n or metadata.top_n or 10),
            monitor_index=locator.monitor_index if locator.monitor_index is not None else metadata.monitor_index,
            last_known_padding=max(0, locator.last_known_padding if locator.last_known_padding is not None else 96),
            notes=metadata.notes,
            name=metadata.name or asset.reference,
        )

    def _build_search_plan(
        self,
        target: TargetSpec,
        effective: EffectiveTemplateSpec,
        ctx: object,
        query_key: str,
    ) -> list[SearchPlanEntry]:
        bounds = ctx.window_manager.get_virtual_screen().rect
        entries: list[SearchPlanEntry] = []
        seen: set[tuple[int, int, int, int]] = set()

        def add(rect: Rect | None, label: str, priority: int) -> None:
            if rect is None:
                return
            clipped = self._clip_rect(rect, bounds)
            if clipped.width <= 0 or clipped.height <= 0:
                return
            key = (clipped.left, clipped.top, clipped.width, clipped.height)
            if key in seen:
                return
            seen.add(key)
            entries.append(SearchPlanEntry(rect=clipped, label=label, priority=priority))

        last_known = ctx.get_image_last_known_area(query_key) if hasattr(ctx, "get_image_last_known_area") else None
        if last_known is not None:
            add(self._expand_rect(last_known, effective.last_known_padding), "last_known", 0)
        if target.region is not None:
            add(Rect(**target.region) if isinstance(target.region, dict) else ctx.window_manager.normalize_region(target.region), "target_region", 1)
        if effective.search_region_hint is not None:
            try:
                resolved = ctx.resolve_region(effective.search_region_hint)
            except Exception:
                resolved = None
            add(Rect(**resolved) if isinstance(resolved, dict) else None, "hint_region", 2)
        if target.window is not None:
            found = ctx.window_manager.find_window(
                title=target.window.title,
                title_contains=target.window.title_contains,
                class_name=target.window.class_name,
            )
            add(found.rect if found is not None else None, "window", 3)
        if effective.monitor_index is not None:
            try:
                monitor_rect, _, _ = ctx.screen_capture.describe_capture_target(monitor_index=effective.monitor_index)
            except Exception:
                monitor_rect = None
            add(monitor_rect, "monitor", 4)
        add(bounds, "full_screen", 5)
        return sorted(entries, key=lambda item: item.priority)

    def _search_frame(
        self,
        frame_array,
        frame_rect: Rect,
        plan: SearchPlanEntry,
        effective: EffectiveTemplateSpec,
        ctx: object,
    ) -> tuple[list[TemplateMatchCandidate], dict[str, Any]]:
        import cv2
        import numpy

        template_image = self._read_template_image(effective.path, effective.use_grayscale)
        if template_image is None:
            return [], {"failure_reason": "template_load_failed", "top_candidates": [], "heatmap_path": None}
        search_source = self._prepare_search_source(frame_array, effective.use_grayscale)
        mask_image = None
        if effective.use_mask:
            if effective.mask_path is None or not effective.mask_path.exists():
                return [], {"failure_reason": "mask_requested_but_missing", "top_candidates": [], "heatmap_path": None}
            mask_image = self._read_mask_image(effective.mask_path, effective.use_grayscale)
        current_dpi = ctx.window_manager.get_monitor_dpi_for_point(*frame_rect.center)
        scales = build_scale_candidates(
            explicit_scales=effective.scales,
            multi_scale=effective.multi_scale,
            preferred_dpi=effective.preferred_dpi,
            current_dpi=current_dpi,
        )
        method = cv2.TM_CCORR_NORMED if mask_image is not None else cv2.TM_CCOEFF_NORMED
        all_candidates: list[TemplateMatchCandidate] = []
        best_heatmap = None
        best_peak = float("-inf")
        failure_reason = "no_candidates_above_threshold"
        for scale in scales:
            scaled_template = self._scale_image(template_image, scale)
            if scaled_template is None:
                continue
            template_height, template_width = scaled_template.shape[:2]
            search_height, search_width = search_source.shape[:2]
            if template_width > search_width or template_height > search_height:
                failure_reason = "template_larger_than_search_region"
                continue
            scaled_mask = self._scale_mask(mask_image, scaled_template.shape[:2]) if mask_image is not None else None
            result = cv2.matchTemplate(search_source, scaled_template, method, mask=scaled_mask)
            _, max_value, _, _ = cv2.minMaxLoc(result)
            if max_value > best_peak:
                best_peak = float(max_value)
                best_heatmap = result
            positions = numpy.argwhere(result >= effective.threshold)
            if len(positions) == 0:
                continue
            scored: list[tuple[float, int, int]] = []
            for row, col in positions:
                scored.append((float(result[row, col]), int(col), int(row)))
            scored.sort(key=lambda item: item[0], reverse=True)
            for score, x, y in scored[: max(50, effective.top_n * 5)]:
                absolute_bbox = Rect(
                    left=frame_rect.left + x,
                    top=frame_rect.top + y,
                    width=template_width,
                    height=template_height,
                )
                all_candidates.append(
                    TemplateMatchCandidate(
                        bbox=absolute_bbox,
                        score=score,
                        scale=scale,
                        search_region=plan.rect,
                        search_label=plan.label,
                        duplicate_key=f"{absolute_bbox.left}:{absolute_bbox.top}:{template_width}:{template_height}",
                        metadata={
                            "method": "TM_CCORR_NORMED" if mask_image is not None else "TM_CCOEFF_NORMED",
                            "template_size": {"width": template_width, "height": template_height},
                            "monitor_dpi": current_dpi,
                        },
                    )
                )
        filtered = filter_duplicate_candidates(all_candidates)
        chosen = non_max_suppression(filtered, iou_threshold=self.nms_iou_threshold, max_candidates=effective.top_n)
        debug_payload = {
            "failure_reason": None if chosen else failure_reason,
            "top_candidates": [candidate.to_dict() for candidate in chosen[: effective.top_n]],
            "peak_score": best_peak if best_peak != float("-inf") else None,
            "heatmap": best_heatmap,
            "scales": scales,
            "method": "TM_CCORR_NORMED" if mask_image is not None else "TM_CCOEFF_NORMED",
        }
        return chosen, debug_payload

    def _save_debug_artifacts(
        self,
        ctx: object,
        effective: EffectiveTemplateSpec,
        frame,
        plan: SearchPlanEntry,
        payload: dict[str, Any],
    ) -> None:
        import cv2
        import numpy

        debug_dir = ctx.artifacts.debug_path("template_match")
        debug_dir.mkdir(parents=True, exist_ok=True)
        diagnostics = getattr(getattr(ctx, "settings", None), "diagnostics", None)
        if diagnostics is not None and not diagnostics.dump_image_match_candidates:
            return
        max_candidates = diagnostics.max_dump_candidates if diagnostics is not None else effective.top_n
        slug = self._slug(f"{effective.reference}_{frame.screenshot_id}_{plan.label}")
        heatmap_path = None
        heatmap = payload.pop("heatmap", None)
        if heatmap is not None:
            normalized = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(numpy.uint8)
            colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
            destination = debug_dir / f"{slug}_heatmap.png"
            cv2.imwrite(str(destination), colored)
            heatmap_path = str(destination)
        payload["heatmap_path"] = heatmap_path
        payload["chosen_candidate"] = payload["top_candidates"][0] if payload["top_candidates"] else None
        payload["top_candidates"] = payload["top_candidates"][:max_candidates]
        payload["search_region"] = plan.rect.to_dict()
        payload["search_label"] = plan.label
        payload["template"] = effective.reference
        payload["template_path"] = str(effective.path)
        payload["screenshot_id"] = frame.screenshot_id
        debug_json = debug_dir / f"{slug}.json"
        debug_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _query_key(self, effective: EffectiveTemplateSpec, target: TargetSpec) -> str:
        return json.dumps(
            {
                "template": effective.reference,
                "path": str(effective.path),
                "threshold": effective.threshold,
                "theme": effective.preferred_theme,
                "monitor": effective.monitor_index,
                "region": target.region,
            },
            sort_keys=True,
        )

    def _emit_failure(self, ctx: object, template: str, reason: str, payload: dict[str, Any]) -> None:
        self._emit_debug_event(ctx, "template_match_failed", template=template, reason=reason, **payload)

    def _emit_debug_event(self, ctx: object, event_type: str, **payload: Any) -> None:
        if hasattr(ctx, "event_logger"):
            ctx.event_logger.emit(event_type, **payload)

    def _frame_bgr_array(self, frame) -> Any:
        import cv2
        import numpy

        return cv2.cvtColor(numpy.array(frame.image), cv2.COLOR_RGB2BGR)

    def _prepare_search_source(self, frame_array, grayscale: bool):
        import cv2

        if not grayscale:
            return frame_array
        return cv2.cvtColor(frame_array, cv2.COLOR_BGR2GRAY)

    def _read_template_image(self, path: Path, grayscale: bool):
        import cv2

        mode = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
        return cv2.imread(str(path), mode)

    def _read_mask_image(self, path: Path, grayscale: bool):
        import cv2

        mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            return None
        if grayscale:
            return mask
        return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    def _scale_image(self, image, scale: float):
        import cv2

        if image is None:
            return None
        if abs(scale - 1.0) < 0.0001:
            return image
        width = max(1, int(round(image.shape[1] * scale)))
        height = max(1, int(round(image.shape[0] * scale)))
        return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR)

    def _scale_mask(self, mask, template_shape: tuple[int, int]):
        import cv2

        if mask is None:
            return None
        template_height, template_width = template_shape[:2]
        if mask.shape[:2] == (template_height, template_width):
            return mask
        return cv2.resize(mask, (template_width, template_height), interpolation=cv2.INTER_NEAREST)

    def _clip_rect(self, rect: Rect, bounds: Rect) -> Rect:
        left = max(bounds.left, rect.left)
        top = max(bounds.top, rect.top)
        right = min(bounds.right, rect.right)
        bottom = min(bounds.bottom, rect.bottom)
        return Rect(left=left, top=top, width=max(0, right - left), height=max(0, bottom - top))

    def _expand_rect(self, rect: Rect, padding: int) -> Rect:
        return Rect(
            left=rect.left - padding,
            top=rect.top - padding,
            width=rect.width + (padding * 2),
            height=rect.height + (padding * 2),
        )

    def _offset_dict(self, value: Any) -> dict[str, int]:
        if isinstance(value, dict):
            return {"x": int(value.get("x", 0)), "y": int(value.get("y", 0))}
        if hasattr(value, "x") and hasattr(value, "y"):
            return {"x": int(getattr(value, "x", 0)), "y": int(getattr(value, "y", 0))}
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return {"x": int(value[0]), "y": int(value[1])}
        return {"x": 0, "y": 0}

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_") or "template_match"
