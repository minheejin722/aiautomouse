from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.results import Rect
from aiautomouse.engine.targeting import build_text_target
from aiautomouse.platform.screen_capture import CaptureFrame
from aiautomouse.providers.ocr_common import (
    OcrQuery,
    OcrRateLimiter,
    OcrTextResult,
    match_text_result,
    normalize_ocr_text,
    select_best_ocr_result,
)
from aiautomouse.providers.windows_ocr import OcrBackend, WindowsOcrProvider
from aiautomouse.runtime.artifacts import ArtifactManager


@dataclass
class FakeOverlay:
    calls: list[tuple[str, int]] = field(default_factory=list)

    def show_ocr_results(self, results, label="", status="recognized") -> None:
        self.calls.append((label, len(results)))


@dataclass
class FakeContext:
    screen_capture: object
    overlay: FakeOverlay = field(default_factory=FakeOverlay)
    ocr_results: dict[str, list[dict]] = field(default_factory=dict)
    last_known: dict[str, Rect] = field(default_factory=dict)

    def remember_ocr_results(self, key: str, results: list[dict]) -> None:
        self.ocr_results[key] = results

    def get_last_known_area(self, key: str) -> Rect | None:
        return self.last_known.get(key)

    def remember_last_known_area(self, key: str, rect: Rect) -> None:
        self.last_known[key] = rect


class FakeScreenCapture:
    def __init__(self) -> None:
        self.frames = 0
        self.image = Image.new("RGB", (20, 20), color="white")

    def describe_capture_target(self, *, region=None, monitor_index=None, window=None):
        if region is not None:
            return Rect(**region), "region", {}
        return Rect(left=10, top=20, width=20, height=20), "full_screen", {}

    def capture_frame(self, region=None, *, monitor_index=None, window=None, reason="capture") -> CaptureFrame:
        self.frames += 1
        rect, source, metadata = self.describe_capture_target(region=region, monitor_index=monitor_index, window=window)
        return CaptureFrame(
            image=self.image,
            rect=rect,
            screenshot_id=f"{reason}_{self.frames}",
            source=source,
            metadata=metadata,
        )


class FakeBackend(OcrBackend):
    name = "fake"

    def __init__(self, results: list[OcrTextResult]) -> None:
        self.results = results
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def recognize(self, frame: CaptureFrame) -> list[OcrTextResult]:
        self.calls += 1
        return [
            OcrTextResult(
                text=result.text,
                normalized_text=result.normalized_text,
                bbox=result.bbox,
                line_id=result.line_id,
                confidence=result.confidence,
                provider=result.provider,
                screenshot_id=frame.screenshot_id,
            )
            for result in self.results
        ]


def test_normalize_ocr_text_collapses_whitespace_and_casefolds_mixed_text():
    normalized = normalize_ocr_text("  Hello\tWORLD  안녕\n하세요  ")

    assert normalized == "hello world 안녕 하세요"


def test_match_text_result_supports_exact_contains_regex_and_fuzzy():
    result = OcrTextResult(
        text="Upload Complete",
        normalized_text=normalize_ocr_text("Upload Complete"),
        bbox=Rect(0, 0, 10, 10),
        line_id="line-1",
        confidence=0.9,
        provider="ocr:fake",
        screenshot_id="shot-1",
    )

    assert match_text_result(result, OcrQuery(text="upload complete", match_mode="exact")) == 1.0
    assert match_text_result(result, OcrQuery(text="complete", match_mode="contains")) is not None
    assert match_text_result(result, OcrQuery(text=r"upload\s+complete", match_mode="regex")) is not None
    assert match_text_result(result, OcrQuery(text="uplod complete", match_mode="fuzzy", fuzzy_threshold=0.8)) is not None


def test_select_best_ocr_result_prefers_anchor_and_last_known_area():
    results = [
        OcrTextResult("Label", normalize_ocr_text("Label"), Rect(50, 50, 40, 20), "anchor", 0.95, "ocr:fake", "shot"),
        OcrTextResult("Submit", normalize_ocr_text("Submit"), Rect(110, 48, 55, 22), "near", 0.88, "ocr:fake", "shot"),
        OcrTextResult("Submit", normalize_ocr_text("Submit"), Rect(300, 200, 55, 22), "far", 0.99, "ocr:fake", "shot"),
    ]
    query = OcrQuery(
        text="submit",
        anchor_text="label",
        anchor_relative="right_of",
        selection_policy="best_match",
    )
    last_known_area = Rect(100, 40, 90, 40)

    selected = select_best_ocr_result(results, query, last_known_area=last_known_area)

    assert selected is not None
    assert selected.result.line_id == "near"


def test_ocr_rate_limiter_waits_for_min_interval():
    state = {"now": 0.0, "slept": []}

    def clock() -> float:
        return state["now"]

    def sleeper(duration: float) -> None:
        state["slept"].append(duration)
        state["now"] += duration

    limiter = OcrRateLimiter(100, clock=clock, sleeper=sleeper)
    limiter.wait()
    state["now"] = 0.05
    limiter.wait()

    assert state["slept"] == [0.05]


def test_ocr_provider_caches_recognition_and_returns_clickable_target():
    backend = FakeBackend(
        [
            OcrTextResult(
                text="업로드",
                normalized_text=normalize_ocr_text("업로드"),
                bbox=Rect(1, 2, 30, 12),
                line_id="line-1",
                confidence=0.91,
                provider="ocr:fake",
                screenshot_id="seed",
            )
        ]
    )
    provider = WindowsOcrProvider(backends=[backend], rate_limit_ms=0, cache_size=8)
    ctx = FakeContext(screen_capture=FakeScreenCapture())
    target = build_text_target(query="업로드", strategy="ocr", match_mode="exact")

    first = provider.find(target, ctx)
    ctx.last_known.clear()
    second = provider.find(target, ctx)

    assert first is not None
    assert second is not None
    assert backend.calls == 1
    assert first.rect.left == 11
    assert first.rect.top == 22
    assert first.metadata["ocr_result"]["line_id"] == "line-1"
    assert ctx.overlay.calls


def test_build_text_target_attaches_template_fallback():
    target = build_text_target(
        query="완료",
        strategy="ocr",
        fallback_template_id="done_icon",
        fallback_confidence=0.93,
    )

    assert target.ocr_text is not None
    assert target.template is not None
    assert target.template.template_id == "done_icon"
    assert target.template.confidence == 0.93


def test_ocr_provider_writes_raw_debug_dump(tmp_path):
    backend = FakeBackend(
        [
            OcrTextResult(
                text="Upload",
                normalized_text=normalize_ocr_text("Upload"),
                bbox=Rect(1, 2, 30, 12),
                line_id="line-1",
                confidence=0.91,
                provider="ocr:fake",
                screenshot_id="seed",
            )
        ]
    )
    provider = WindowsOcrProvider(backends=[backend], rate_limit_ms=0, cache_size=8)
    ctx = FakeContext(screen_capture=FakeScreenCapture())
    ctx.settings = AppSettings.from_dict({"paths": {"artifacts_dir": str(tmp_path / "logs" / "runs")}})
    ctx.artifacts = ArtifactManager(tmp_path / "logs" / "runs" / "ocr-debug")
    target = build_text_target(query="Upload", strategy="ocr", match_mode="exact")

    match = provider.find(target, ctx)
    dump_files = sorted((ctx.artifacts.run_dir / "debug" / "ocr").glob("*.json"))

    assert match is not None
    assert len(dump_files) == 1
    assert Path(dump_files[0]).read_text(encoding="utf-8")
