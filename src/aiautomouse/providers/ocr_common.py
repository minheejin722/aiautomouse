from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable

from aiautomouse.engine.results import Rect, TargetMatch


def normalize_ocr_text(
    text: str,
    *,
    collapse_whitespace: bool = True,
    casefold_text: bool = True,
) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u200b", "").replace("\ufeff", "")
    if collapse_whitespace:
        normalized = re.sub(r"\s+", " ", normalized).strip()
    if casefold_text:
        normalized = normalized.casefold()
    return normalized


@dataclass(frozen=True)
class OcrQuery:
    text: str
    match_mode: str = "contains"
    case_sensitive: bool = False
    collapse_whitespace: bool = True
    fuzzy_threshold: float = 0.75
    anchor_text: str | None = None
    anchor_match_mode: str = "contains"
    anchor_relative: str = "any"
    anchor_max_distance: int = 400
    selection_policy: str = "best_match"
    last_known_padding: int = 96

    def normalized_query(self) -> str:
        return normalize_ocr_text(
            self.text,
            collapse_whitespace=self.collapse_whitespace,
            casefold_text=not self.case_sensitive,
        )

    def normalized_anchor_query(self) -> str | None:
        if not self.anchor_text:
            return None
        return normalize_ocr_text(
            self.anchor_text,
            collapse_whitespace=self.collapse_whitespace,
            casefold_text=not self.case_sensitive,
        )

    def signature(self) -> str:
        return hashlib.sha1(
            json.dumps(asdict(self), sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class OcrTextResult:
    text: str
    normalized_text: str
    bbox: Rect
    line_id: str
    confidence: float
    provider: str
    screenshot_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = self.bbox.to_dict()
        return payload

    def to_target_match(self) -> TargetMatch:
        return TargetMatch(
            provider_name=self.provider,
            rect=self.bbox,
            confidence=self.confidence,
            text=self.text,
            metadata={
                "ocr_result": self.to_dict(),
                "normalized_text": self.normalized_text,
                "line_id": self.line_id,
                "provider": self.provider,
                "screenshot_id": self.screenshot_id,
            },
        )


@dataclass(frozen=True)
class OcrSelection:
    result: OcrTextResult
    match_score: float
    anchor_score: float
    last_known_hit: bool
    index: int


class OcrResultCache:
    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max(1, max_entries)
        self._values: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Any:
        if key not in self._values:
            return None
        value = self._values.pop(key)
        self._values[key] = value
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._values:
            self._values.pop(key)
        self._values[key] = value
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)


class OcrRateLimiter:
    def __init__(
        self,
        min_interval_ms: int = 0,
        *,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.min_interval_ms = max(0, int(min_interval_ms))
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        if self.min_interval_ms <= 0:
            return
        now = self._clock()
        if now < self._next_allowed_at:
            self._sleeper(self._next_allowed_at - now)
            now = self._clock()
        self._next_allowed_at = now + (self.min_interval_ms / 1000.0)


def match_text_result(result: OcrTextResult, query: OcrQuery, *, anchor_search: bool = False) -> float | None:
    match_mode = query.anchor_match_mode if anchor_search else query.match_mode
    raw_query = query.anchor_text if anchor_search else query.text
    if not raw_query:
        return None
    candidate = normalize_ocr_text(
        result.text,
        collapse_whitespace=query.collapse_whitespace,
        casefold_text=not query.case_sensitive,
    )
    expected = normalize_ocr_text(
        raw_query,
        collapse_whitespace=query.collapse_whitespace,
        casefold_text=not query.case_sensitive,
    )
    if not candidate or not expected:
        return None
    if match_mode == "exact":
        return 1.0 if candidate == expected else None
    if match_mode == "contains":
        if expected not in candidate:
            return None
        return min(1.0, len(expected) / max(len(candidate), 1))
    if match_mode == "regex":
        flags = 0
        matched = re.search(expected, candidate, flags=flags)
        if matched is None:
            return None
        return min(1.0, len(matched.group(0)) / max(len(candidate), 1))
    if match_mode == "fuzzy":
        if expected in candidate:
            return 1.0
        score = SequenceMatcher(None, expected, candidate).ratio()
        return score if score >= query.fuzzy_threshold else None
    raise ValueError(f"Unsupported OCR match mode: {match_mode}")


def select_best_ocr_result(
    results: list[OcrTextResult],
    query: OcrQuery,
    *,
    last_known_area: Rect | None = None,
) -> OcrSelection | None:
    anchor = _find_anchor(results, query)
    ranked: list[OcrSelection] = []
    for index, result in enumerate(results):
        match_score = match_text_result(result, query)
        if match_score is None:
            continue
        anchor_score = _anchor_score(result.bbox, anchor.bbox if anchor else None, query)
        if anchor is not None and query.anchor_relative != "any" and anchor_score <= 0:
            continue
        last_known_hit = _rect_intersects(result.bbox, last_known_area) if last_known_area else False
        ranked.append(
            OcrSelection(
                result=result,
                match_score=match_score,
                anchor_score=anchor_score,
                last_known_hit=last_known_hit,
                index=index,
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: _selection_key(item, query), reverse=True)
    return ranked[0]


def expand_rect(rect: Rect, padding: int, *, bounds: Rect | None = None) -> Rect:
    expanded = Rect(
        left=rect.left - padding,
        top=rect.top - padding,
        width=rect.width + (padding * 2),
        height=rect.height + (padding * 2),
    )
    if bounds is None:
        return expanded
    left = max(bounds.left, expanded.left)
    top = max(bounds.top, expanded.top)
    right = min(bounds.right, expanded.right)
    bottom = min(bounds.bottom, expanded.bottom)
    return Rect(left=left, top=top, width=max(1, right - left), height=max(1, bottom - top))


def _find_anchor(results: list[OcrTextResult], query: OcrQuery) -> OcrTextResult | None:
    if not query.anchor_text:
        return None
    anchor_candidates: list[tuple[float, float, int, OcrTextResult]] = []
    for index, result in enumerate(results):
        score = match_text_result(result, query, anchor_search=True)
        if score is None:
            continue
        anchor_candidates.append((score, result.confidence, -index, result))
    if not anchor_candidates:
        return None
    anchor_candidates.sort(reverse=True)
    return anchor_candidates[0][3]


def _selection_key(item: OcrSelection, query: OcrQuery) -> tuple[float, ...]:
    if query.selection_policy == "first":
        return (1.0 if item.last_known_hit else 0.0, -item.index)
    if query.selection_policy == "highest_confidence":
        return (
            1.0 if item.last_known_hit else 0.0,
            item.confidence,
            item.match_score,
            item.anchor_score,
            -item.index,
        )
    if query.selection_policy == "last_known_area":
        return (
            1.0 if item.last_known_hit else 0.0,
            item.match_score,
            item.anchor_score,
            item.result.confidence,
            -item.index,
        )
    if query.selection_policy == "nearest_anchor":
        return (
            item.anchor_score,
            1.0 if item.last_known_hit else 0.0,
            item.match_score,
            item.result.confidence,
            -item.index,
        )
    return (
        1.0 if item.last_known_hit else 0.0,
        item.anchor_score,
        item.match_score,
        item.result.confidence,
        -item.index,
    )


def _anchor_score(candidate: Rect, anchor: Rect | None, query: OcrQuery) -> float:
    if anchor is None:
        return 0.0
    distance = _relative_distance(candidate, anchor, query.anchor_relative)
    if distance is None or distance > query.anchor_max_distance:
        return 0.0
    return 1.0 / (1.0 + distance)


def _relative_distance(candidate: Rect, anchor: Rect, relation: str) -> float | None:
    candidate_center_x, candidate_center_y = candidate.center
    anchor_center_x, anchor_center_y = anchor.center
    dx = candidate_center_x - anchor_center_x
    dy = candidate_center_y - anchor_center_y
    horizontal_gap = max(0, anchor.left - candidate.right, candidate.left - anchor.right)
    vertical_gap = max(0, anchor.top - candidate.bottom, candidate.top - anchor.bottom)
    euclidean = math.sqrt((dx * dx) + (dy * dy))
    if relation == "any":
        return euclidean
    if relation == "left_of":
        if candidate_center_x >= anchor_center_x:
            return None
        return math.sqrt((horizontal_gap * horizontal_gap) + (dy * dy))
    if relation == "right_of":
        if candidate_center_x <= anchor_center_x:
            return None
        return math.sqrt((horizontal_gap * horizontal_gap) + (dy * dy))
    if relation == "above":
        if candidate_center_y >= anchor_center_y:
            return None
        return math.sqrt((vertical_gap * vertical_gap) + (dx * dx))
    if relation == "below":
        if candidate_center_y <= anchor_center_y:
            return None
        return math.sqrt((vertical_gap * vertical_gap) + (dx * dx))
    if relation == "near":
        return euclidean
    raise ValueError(f"Unsupported anchor relation: {relation}")


def _rect_intersects(first: Rect, second: Rect | None) -> bool:
    if second is None:
        return False
    return not (
        first.right <= second.left
        or first.left >= second.right
        or first.bottom <= second.top
        or first.top >= second.bottom
    )
