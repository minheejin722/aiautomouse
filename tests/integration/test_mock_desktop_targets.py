from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.context import RunMode, RuntimeContext
from aiautomouse.engine.models import (
    ClickRefStep,
    FindTextStep,
    FocusWindowStep,
    MacroSpec,
    PasteSnippetStep,
    PressKeysStep,
    RefExistsCondition,
    VerifyAllStep,
)
from aiautomouse.engine.results import Rect, StepStatus, TargetMatch
from aiautomouse.engine.runner import MacroRunner
from aiautomouse.engine.resolver import TargetResolver
from aiautomouse.platform.screen_capture import CaptureFrame
from aiautomouse.providers.base import LocatorProvider
from aiautomouse.runtime.artifacts import ArtifactManager
from aiautomouse.runtime.logging import StructuredEventLogger

pytestmark = pytest.mark.integration


class FakeTextProvider(LocatorProvider):
    name = "fake_text"
    supported_fields = ("ocr_text",)

    def is_available(self) -> bool:
        return True

    def find(self, target, ctx):
        return TargetMatch(
            provider_name=self.name,
            rect=Rect(left=24, top=18, width=40, height=16),
            confidence=0.99,
            text=str(target.ocr_text.text),
        )


class FakeWindow:
    def __init__(self) -> None:
        self.rect = Rect(left=0, top=0, width=128, height=96)

    def to_dict(self):
        return {"title": "Mock Chrome", "class_name": "MockWindow", "rect": self.rect.to_dict()}


class FakeWindowManager:
    def __init__(self) -> None:
        self.window = FakeWindow()

    def get_active_window_title(self):
        return "Mock Chrome"

    def get_active_window_info(self):
        return self.window.to_dict()

    def focus_window(self, title=None, title_contains=None, class_name=None):
        if title_contains and "chrome" not in title_contains.lower():
            return None
        return self.window.to_dict()

    def find_window(self, title=None, title_contains=None, class_name=None):
        if title_contains and "chrome" not in title_contains.lower():
            return None
        return self.window

    def get_virtual_screen(self):
        return type("VirtualScreen", (), {"rect": Rect(left=0, top=0, width=128, height=96)})()

    def normalize_region(self, region):
        if region is None:
            return None
        if isinstance(region, Rect):
            return region
        return Rect(**region)


class FakeScreenCapture:
    def __init__(self) -> None:
        self.counter = 0
        self.image = Image.new("RGB", (128, 96), color="white")

    def capture(self, region=None):
        return self.capture_frame(region=region).image

    def capture_frame(self, region=None, *, monitor_index=None, window=None, reason="capture"):
        self.counter += 1
        rect = Rect(left=0, top=0, width=128, height=96)
        if region is not None:
            rect = Rect(**region) if isinstance(region, dict) else region
        elif window is not None:
            rect = Rect(**window["rect"]) if isinstance(window, dict) else window.rect
        return CaptureFrame(
            image=self.image.copy(),
            rect=rect,
            screenshot_id=f"{reason}_{self.counter}",
            source="mock",
            metadata={},
        )

    def save(self, image, path):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination)
        return destination


class FakeStopToken:
    def is_set(self):
        return False


class FakeOverlay:
    def show_target(self, match, label="", status="planned"):
        return None


class FakeSnippets:
    def get(self, name):
        return f"snippet:{name}"


class FakeTemplates:
    def get(self, name):
        raise KeyError(name)


class RecordingInputController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def click(self, x, y, button="left"):
        self.calls.append(("click", {"x": x, "y": y, "button": button}))

    def paste_text(self, text):
        self.calls.append(("paste_text", text))

    def hotkey(self, keys):
        self.calls.append(("hotkey", keys))

    def get_clipboard_text(self):
        return "before"


def test_mock_desktop_flow_writes_replay_logs_and_step_artifacts(tmp_path):
    settings = AppSettings.from_dict(
        {
            "poll_interval_ms": 0,
            "paths": {
                "logs_dir": str(tmp_path / "logs"),
                "artifacts_dir": str(tmp_path / "logs" / "runs"),
            },
        }
    )
    artifacts = ArtifactManager(settings.paths.artifacts_dir / "mock_run")
    event_logger = StructuredEventLogger(artifacts.events_path)
    macro = MacroSpec(
        name="mock_upload",
        steps=[
            FocusWindowStep(type="focus_window", id="focus", title_contains="Chrome"),
            FindTextStep(type="find_text", id="find_upload", query="업로드", strategy="ocr", save_as="upload_btn"),
            ClickRefStep(type="click_ref", id="click_upload", ref="upload_btn"),
            PasteSnippetStep(type="paste_snippet", id="paste_prompt", snippet_id="prompt_01"),
            PressKeysStep(type="press_keys", id="confirm", keys="enter"),
            VerifyAllStep(
                type="verify_all",
                id="verify",
                conditions=[RefExistsCondition(type="ref_exists", ref="upload_btn")],
            ),
        ],
    )
    ctx = RuntimeContext(
        settings=settings,
        mode=RunMode.EXECUTE,
        resolver=TargetResolver([FakeTextProvider()]),
        artifacts=artifacts,
        event_logger=event_logger,
        overlay=FakeOverlay(),
        stop_token=FakeStopToken(),
        input_controller=RecordingInputController(),
        window_manager=FakeWindowManager(),
        screen_capture=FakeScreenCapture(),
        snippets=FakeSnippets(),
        templates=FakeTemplates(),
        macro_path=tmp_path / "mock_upload.json",
        macro=macro,
        run_id="mock_run",
    )

    result = MacroRunner().run(macro, ctx)

    summary = json.loads((artifacts.run_dir / "summary.json").read_text(encoding="utf-8"))
    events = (artifacts.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    step_snapshots = sorted((artifacts.run_dir / "debug" / "steps").glob("*.json"))
    screenshots = sorted((artifacts.run_dir / "screenshots").glob("*.png"))

    assert result.status == StepStatus.SUCCESS
    assert result.failed_step_id is None
    assert summary["status"] == "success"
    assert summary["replay_log"].endswith("events.jsonl")
    assert "mock_upload.find_upload" in summary["step_timings"]
    assert any(event for event in events if '"sequence": 1' in event)
    assert any(event for event in events if '"event": "macro_finished"' in event)
    assert any(name == "click" for name, _ in ctx.input_controller.calls)
    assert any(name == "paste_text" for name, _ in ctx.input_controller.calls)
    assert any(name == "hotkey" for name, _ in ctx.input_controller.calls)
    assert len(step_snapshots) >= 2
    assert len(screenshots) >= 2
