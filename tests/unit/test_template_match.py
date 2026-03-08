from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from aiautomouse.engine.actions import ActionExecutor
from aiautomouse.engine.results import Rect, TargetMatch
from aiautomouse.engine.targeting import build_image_target
from aiautomouse.platform.screen_capture import CaptureFrame
from aiautomouse.providers.image_match_common import (
    TemplateMatchCandidate,
    build_scale_candidates,
    filter_duplicate_candidates,
    non_max_suppression,
)
from aiautomouse.providers.template_match import TemplateMatchProvider
from aiautomouse.resources.templates import TemplateStore


@dataclass
class FakeArtifacts:
    root: Path

    def debug_path(self, *parts: str) -> Path:
        destination = self.root.joinpath(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination


@dataclass
class FakeEventLogger:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def emit(self, event_type: str, **payload):
        self.events.append((event_type, payload))
        return {"event": event_type, **payload}


@dataclass
class FakeWindowInfo:
    rect: Rect


class FakeWindowManager:
    def __init__(self, virtual_rect: Rect, dpi: int = 144) -> None:
        self.virtual_rect = virtual_rect
        self.dpi = dpi

    def get_virtual_screen(self):
        return type("VirtualScreen", (), {"rect": self.virtual_rect})()

    def normalize_region(self, region):
        if region is None:
            return None
        if isinstance(region, Rect):
            return region
        if isinstance(region, dict):
            return Rect(**region)
        raise ValueError(region)

    def find_window(self, title=None, title_contains=None, class_name=None):
        return FakeWindowInfo(self.virtual_rect)

    def get_monitor_dpi_for_point(self, x: int, y: int) -> int:
        return self.dpi


class FakeScreenCapture:
    def __init__(self, base_image: Image.Image, virtual_rect: Rect) -> None:
        self.base_image = base_image
        self.virtual_rect = virtual_rect
        self.requests: list[Rect] = []
        self.counter = 0

    def capture_frame(self, region=None, *, monitor_index=None, window=None, reason="capture") -> CaptureFrame:
        if region is None:
            rect = self.virtual_rect
        else:
            rect = Rect(**region)
        self.requests.append(rect)
        self.counter += 1
        local_left = rect.left - self.virtual_rect.left
        local_top = rect.top - self.virtual_rect.top
        crop = self.base_image.crop((local_left, local_top, local_left + rect.width, local_top + rect.height))
        return CaptureFrame(image=crop, rect=rect, screenshot_id=f"{reason}_{self.counter}", source="region", metadata={})

    def describe_capture_target(self, *, region=None, monitor_index=None, window=None):
        if region is not None:
            return Rect(**region), "region", {}
        if monitor_index is not None:
            return self.virtual_rect, "monitor", {"monitor_index": monitor_index}
        return self.virtual_rect, "full_screen", {}


@dataclass
class FakeContext:
    templates: TemplateStore
    screen_capture: FakeScreenCapture
    window_manager: FakeWindowManager
    artifacts: FakeArtifacts
    event_logger: FakeEventLogger = field(default_factory=FakeEventLogger)
    image_last_known_areas: dict[str, Rect] = field(default_factory=dict)
    image_results: dict[str, list[dict]] = field(default_factory=dict)
    named_regions: dict[str, dict[str, int]] = field(default_factory=dict)

    def get_image_last_known_area(self, key: str) -> Rect | None:
        return self.image_last_known_areas.get(key)

    def remember_image_last_known_area(self, key: str, rect: Rect) -> None:
        self.image_last_known_areas[key] = rect

    def remember_image_results(self, key: str, results: list[dict]) -> None:
        self.image_results[key] = results

    def resolve_region(self, region):
        if isinstance(region, str):
            return self.named_regions[region]
        if isinstance(region, dict):
            return region
        raise ValueError(region)


def test_template_store_merges_sidecar_metadata(tmp_path):
    template_path = tmp_path / "button.png"
    Image.new("RGB", (12, 12), "white").save(template_path)
    (tmp_path / "button.template.json").write_text(
        json.dumps(
            {
                "preferred_theme": "dark",
                "click_offset": {"x": 4, "y": -2},
                "use_mask": True,
            }
        ),
        encoding="utf-8",
    )
    store = TemplateStore(
        tmp_path,
        {
            "button": {
                "path": "button.png",
                "threshold": 0.93,
                "name": "Primary Button",
            }
        },
    )

    asset = store.get("button")

    assert asset.path == template_path
    assert asset.metadata.threshold == 0.93
    assert asset.metadata.preferred_theme == "dark"
    assert getattr(asset.metadata.click_offset, "x", None) == 4
    assert getattr(asset.metadata.click_offset, "y", None) == -2
    assert asset.metadata.name == "Primary Button"


def test_candidate_filters_apply_duplicate_filtering_and_nms():
    candidates = [
        TemplateMatchCandidate(Rect(10, 10, 20, 20), 0.95, 1.0, Rect(0, 0, 100, 100), "full"),
        TemplateMatchCandidate(Rect(11, 10, 20, 20), 0.93, 1.0, Rect(0, 0, 100, 100), "full"),
        TemplateMatchCandidate(Rect(60, 60, 20, 20), 0.91, 1.0, Rect(0, 0, 100, 100), "full"),
    ]

    filtered = filter_duplicate_candidates(candidates)
    kept = non_max_suppression(filtered, max_candidates=5)

    assert len(filtered) == 2
    assert len(kept) == 2
    assert kept[0].bbox.left == 10
    assert kept[1].bbox.left == 60


def test_build_scale_candidates_uses_monitor_dpi_hint():
    scales = build_scale_candidates(explicit_scales=[], multi_scale=True, preferred_dpi=96, current_dpi=144)

    assert scales[0] < 1.5
    assert 1.5 in scales
    assert scales[-1] > 1.5


def test_template_provider_prefers_last_known_region_and_reuses_unchanged_frame(tmp_path):
    virtual_rect = Rect(left=-100, top=0, width=220, height=120)
    base = Image.new("RGB", (220, 120), "white")
    draw = ImageDraw.Draw(base)
    draw.rectangle((140, 40, 170, 70), fill="red", outline="black")
    template_path = tmp_path / "button.png"
    base.crop((140, 40, 171, 71)).save(template_path)
    store = TemplateStore(tmp_path, {"button": {"path": "button.png", "click_offset": {"x": 3, "y": -1}}})
    ctx = FakeContext(
        templates=store,
        screen_capture=FakeScreenCapture(base, virtual_rect),
        window_manager=FakeWindowManager(virtual_rect),
        artifacts=FakeArtifacts(tmp_path / "artifacts"),
    )
    provider = TemplateMatchProvider(diff_threshold=0.02)
    target = build_image_target(template_id="button", confidence=0.9, monitor_index=0, last_known_padding=20)

    first = provider.find(target, ctx)
    second = provider.find(target, ctx)

    assert first is not None
    assert second is not None
    assert first.rect.left == 40
    assert first.rect.top == 40
    assert first.metadata["click_offset"] == {"x": 3, "y": -1}
    assert ctx.screen_capture.requests[0] == virtual_rect
    assert ctx.screen_capture.requests[1].width < virtual_rect.width
    assert ctx.screen_capture.requests[1].height < virtual_rect.height

    original = provider._search_frame

    def fail_search(*args, **kwargs):
        raise AssertionError("search should have been skipped via frame differencing")

    provider._search_frame = fail_search
    try:
        third = provider.find(target, ctx)
    finally:
        provider._search_frame = original

    assert third is not None
    assert any(event[0] == "template_match_frame_reused" for event in ctx.event_logger.events)


def test_template_provider_writes_debug_artifacts_and_respects_mask(tmp_path):
    virtual_rect = Rect(left=0, top=0, width=120, height=80)
    base = Image.new("RGB", (120, 80), "gray")
    draw = ImageDraw.Draw(base)
    draw.rectangle((40, 20, 69, 49), fill="blue")
    draw.rectangle((48, 28, 61, 41), fill="yellow")
    template = Image.new("RGB", (30, 30), "black")
    template_draw = ImageDraw.Draw(template)
    template_draw.rectangle((0, 0, 29, 29), fill="black")
    template_draw.rectangle((8, 8, 21, 21), fill="yellow")
    template_path = tmp_path / "icon.png"
    template.save(template_path)
    mask = Image.new("L", (30, 30), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rectangle((8, 8, 21, 21), fill=255)
    mask_path = tmp_path / "icon.mask.png"
    mask.save(mask_path)
    (tmp_path / "icon.template.json").write_text(
        json.dumps({"use_mask": True, "use_grayscale": False, "threshold": 0.9}),
        encoding="utf-8",
    )
    store = TemplateStore(tmp_path, {"icon": "icon.png"})
    ctx = FakeContext(
        templates=store,
        screen_capture=FakeScreenCapture(base, virtual_rect),
        window_manager=FakeWindowManager(virtual_rect, dpi=120),
        artifacts=FakeArtifacts(tmp_path / "artifacts"),
    )
    provider = TemplateMatchProvider()

    match = provider.find(build_image_target(template_id="icon", confidence=0.9), ctx)

    assert match is not None
    debug_dir = tmp_path / "artifacts" / "template_match"
    assert any(path.suffix == ".png" for path in debug_dir.iterdir())
    assert any(path.suffix == ".json" for path in debug_dir.iterdir())
    assert match.metadata["chosen_candidate"]["metadata"]["monitor_dpi"] == 120


def test_action_executor_uses_template_click_offset_metadata():
    match = TargetMatch(
        provider_name="template_match",
        rect=Rect(10, 10, 20, 20),
        confidence=0.99,
        metadata={"click_offset": {"x": 4, "y": -3}},
    )

    point = ActionExecutor()._point_from_match(match, None)

    assert point == (24, 17)
