from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from aiautomouse.engine.results import Rect


@dataclass(frozen=True)
class TemplateMatchCandidate:
    bbox: Rect
    score: float
    scale: float
    search_region: Rect
    search_label: str
    duplicate_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox": self.bbox.to_dict(),
            "score": self.score,
            "scale": self.scale,
            "search_region": self.search_region.to_dict(),
            "search_label": self.search_label,
            "duplicate_key": self.duplicate_key,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SearchPlanEntry:
    rect: Rect
    label: str
    priority: int


def build_scale_candidates(
    *,
    explicit_scales: list[float],
    multi_scale: bool,
    preferred_dpi: int | None,
    current_dpi: int,
) -> list[float]:
    if explicit_scales:
        scales = explicit_scales
    else:
        base_scale = 1.0
        if preferred_dpi and preferred_dpi > 0:
            base_scale = current_dpi / float(preferred_dpi)
        if not multi_scale:
            scales = [base_scale]
        else:
            scales = [base_scale * factor for factor in (0.85, 0.95, 1.0, 1.05, 1.15)]
    deduped: list[float] = []
    seen: set[float] = set()
    for scale in scales:
        normalized = round(max(0.1, float(scale)), 4)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def non_max_suppression(
    candidates: list[TemplateMatchCandidate],
    *,
    iou_threshold: float = 0.35,
    max_candidates: int = 10,
) -> list[TemplateMatchCandidate]:
    ordered = sorted(candidates, key=lambda item: item.score, reverse=True)
    kept: list[TemplateMatchCandidate] = []
    for candidate in ordered:
        if any(intersection_over_union(candidate.bbox, existing.bbox) >= iou_threshold for existing in kept):
            continue
        kept.append(candidate)
        if len(kept) >= max_candidates:
            break
    return kept


def filter_duplicate_candidates(
    candidates: list[TemplateMatchCandidate],
    *,
    distance_ratio: float = 0.25,
) -> list[TemplateMatchCandidate]:
    ordered = sorted(candidates, key=lambda item: item.score, reverse=True)
    kept: list[TemplateMatchCandidate] = []
    for candidate in ordered:
        if any(_is_duplicate(candidate, existing, distance_ratio=distance_ratio) for existing in kept):
            continue
        kept.append(candidate)
    return kept


def intersection_over_union(first: Rect, second: Rect) -> float:
    inter_left = max(first.left, second.left)
    inter_top = max(first.top, second.top)
    inter_right = min(first.right, second.right)
    inter_bottom = min(first.bottom, second.bottom)
    if inter_right <= inter_left or inter_bottom <= inter_top:
        return 0.0
    inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
    first_area = first.width * first.height
    second_area = second.width * second.height
    union = first_area + second_area - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def frame_difference_score(previous_frame, current_frame) -> float:
    import cv2
    import numpy

    previous_gray = _as_gray(previous_frame)
    current_gray = _as_gray(current_frame)
    size = (64, 64)
    previous_small = cv2.resize(previous_gray, size, interpolation=cv2.INTER_AREA)
    current_small = cv2.resize(current_gray, size, interpolation=cv2.INTER_AREA)
    difference = cv2.absdiff(previous_small, current_small)
    return float(numpy.mean(difference) / 255.0)


def relative_region_from_anchor(anchor: Rect, relation: str, padding: int = 120) -> Rect:
    pad = max(0, int(padding))
    if relation == "left_of":
        return Rect(left=anchor.left - anchor.width - pad, top=anchor.top - pad, width=anchor.width + (pad * 2), height=anchor.height + (pad * 2))
    if relation == "right_of":
        return Rect(left=anchor.right - pad, top=anchor.top - pad, width=anchor.width + (pad * 2), height=anchor.height + (pad * 2))
    if relation == "above":
        return Rect(left=anchor.left - pad, top=anchor.top - anchor.height - pad, width=anchor.width + (pad * 2), height=anchor.height + (pad * 2))
    if relation == "below":
        return Rect(left=anchor.left - pad, top=anchor.bottom - pad, width=anchor.width + (pad * 2), height=anchor.height + (pad * 2))
    return Rect(left=anchor.left - pad, top=anchor.top - pad, width=anchor.width + (pad * 2), height=anchor.height + (pad * 2))


def _is_duplicate(candidate: TemplateMatchCandidate, existing: TemplateMatchCandidate, *, distance_ratio: float) -> bool:
    if candidate.duplicate_key and candidate.duplicate_key == existing.duplicate_key:
        return True
    iou = intersection_over_union(candidate.bbox, existing.bbox)
    if iou >= 0.6:
        return True
    center_distance = _center_distance(candidate.bbox, existing.bbox)
    tolerance = max(4.0, min(candidate.bbox.width, candidate.bbox.height) * distance_ratio)
    return center_distance <= tolerance


def _center_distance(first: Rect, second: Rect) -> float:
    first_x, first_y = first.center
    second_x, second_y = second.center
    return math.sqrt(((first_x - second_x) ** 2) + ((first_y - second_y) ** 2))


def _as_gray(frame) -> Any:
    import cv2

    if len(frame.shape) == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
