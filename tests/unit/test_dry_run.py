from __future__ import annotations

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.context import RunMode, RuntimeContext
from aiautomouse.engine.models import FindTextStep, MacroSpec, PasteSnippetStep
from aiautomouse.engine.results import Rect, StepStatus, TargetMatch
from aiautomouse.engine.runner import MacroRunner


class FakeArtifacts:
    def write_json(self, name, payload):
        return name

    def capture_failure_screenshot(self, step_id, screen_capture):
        return None

    def capture_named_screenshot(self, name, screen_capture):
        return None


class FakeLogger:
    def emit(self, event_type, **payload):
        return {"event": event_type, **payload}


class FakeOverlay:
    def show_target(self, match, label="", status="planned"):
        return None


class FakeStopToken:
    def is_set(self):
        return False


class FakeResolver:
    def resolve(self, target, ctx):
        return TargetMatch("windows_uia", Rect(10, 20, 30, 40), 1.0, text="Editor")


class FakeWindowManager:
    def get_active_window_info(self):
        return {"title": "Editor", "class_name": "Editor"}

    def get_active_window_title(self):
        return "Editor"


class FakeCapture:
    pass


class FakeSnippets:
    def get(self, name):
        return "snippet text"


class FakeTemplates:
    def resolve(self, reference):
        return reference


class RecordingInputController:
    def __init__(self):
        self.calls = []

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))

    def paste_text(self, *args, **kwargs):
        self.calls.append(("paste_text", args, kwargs))

    def hotkey(self, *args, **kwargs):
        self.calls.append(("hotkey", args, kwargs))

    def get_clipboard_text(self):
        return "before"


def test_dry_run_preserves_clipboard_state_and_skips_input_calls():
    macro = MacroSpec(
        name="paste_macro",
        steps=[
            FindTextStep(type="find_text", id="find_editor", query="Editor", save_as="editor"),
            PasteSnippetStep(type="paste_snippet", id="paste", snippet_id="prompt_01", ref="editor"),
        ],
    )
    ctx = RuntimeContext(
        settings=AppSettings.from_dict({"poll_interval_ms": 0}),
        mode=RunMode.DRY_RUN,
        resolver=FakeResolver(),
        artifacts=FakeArtifacts(),
        event_logger=FakeLogger(),
        overlay=FakeOverlay(),
        stop_token=FakeStopToken(),
        input_controller=RecordingInputController(),
        window_manager=FakeWindowManager(),
        screen_capture=FakeCapture(),
        snippets=FakeSnippets(),
        templates=FakeTemplates(),
        macro_path="macro.yaml",
        macro=macro,
    )
    runner = MacroRunner()

    result = runner.run(macro, ctx)

    assert result.status == StepStatus.SUCCESS
    assert ctx.clipboard_state["before"] == "before"
    assert ctx.clipboard_state["after"] == "snippet text"
    assert ctx.input_controller.calls == []
