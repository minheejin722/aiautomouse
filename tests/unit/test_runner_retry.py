from __future__ import annotations

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.context import RunMode, RuntimeContext
from aiautomouse.engine.models import (
    CallSubmacroStep,
    ClickRefStep,
    FindTextStep,
    FocusWindowStep,
    MacroSpec,
    PressKeysStep,
    RefExistsCondition,
    RetryPolicySpec,
    StepSucceededCondition,
    SubmacroSpec,
    VerifyAllStep,
)
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
        if target.ocr_text:
            text = target.ocr_text.text
        elif target.uia and target.uia.name_contains:
            text = target.uia.name_contains
        elif target.dom and target.dom.text:
            text = target.dom.text
        else:
            text = "target"
        return TargetMatch("windows_uia", Rect(10, 20, 40, 30), 1.0, text=text)


class FakeWindowManager:
    def __init__(self):
        self.focus_attempts = 0

    def get_active_window_title(self):
        return "Chrome"

    def get_active_window_info(self):
        return {"title": "Chrome", "class_name": "Chrome_WidgetWin_1"}

    def focus_window(self, title=None, title_contains=None, class_name=None):
        self.focus_attempts += 1
        if self.focus_attempts == 1:
            return None
        return {"title": title or title_contains or "", "class_name": class_name or "Chrome_WidgetWin_1"}

    def find_window(self, title=None, title_contains=None, class_name=None):
        return type("Window", (), {"to_dict": lambda self: {"title": "Chrome"}, "title": "Chrome", "class_name": "Chrome_WidgetWin_1"})()


class FakeCapture:
    pass


class FakeSnippets:
    def get(self, name):
        return f"snippet:{name}"


class FakeTemplates:
    def resolve(self, reference):
        return reference


class RecordingInputController:
    def __init__(self):
        self.calls = []

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))

    def double_click(self, *args, **kwargs):
        self.calls.append(("double_click", args, kwargs))

    def move_mouse(self, *args, **kwargs):
        self.calls.append(("move_mouse", args, kwargs))

    def type_text(self, *args, **kwargs):
        self.calls.append(("type_text", args, kwargs))

    def paste_text(self, *args, **kwargs):
        self.calls.append(("paste_text", args, kwargs))

    def hotkey(self, *args, **kwargs):
        self.calls.append(("hotkey", args, kwargs))

    def get_clipboard_text(self):
        return "before"


def make_context(macro, mode=RunMode.DRY_RUN):
    return RuntimeContext(
        settings=AppSettings.from_dict({"poll_interval_ms": 0}),
        mode=mode,
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


def test_runner_applies_retry_policy_to_focus_window_step():
    macro = MacroSpec(
        name="retry_focus",
        steps=[
            FocusWindowStep(
                type="focus_window",
                id="focus_chrome",
                title_contains="Chrome",
                retry=RetryPolicySpec(max_attempts=2, delay_ms=0),
            )
        ],
    )
    ctx = make_context(macro, mode=RunMode.EXECUTE)
    runner = MacroRunner()

    result = runner.run(macro, ctx)

    assert result.status == StepStatus.SUCCESS
    assert result.steps[-1].attempts == 2
    assert ctx.window_manager.focus_attempts == 2


def test_runner_preserves_refs_and_submacro_context():
    macro = MacroSpec(
        name="upload_flow",
        variables={"button_label": "업로드"},
        submacros={
            "submit": SubmacroSpec(
                variables={"confirmation": "done"},
                steps=[
                    PressKeysStep(type="press_keys", id="press_enter", keys="enter"),
                    VerifyAllStep(
                        type="verify_all",
                        id="submacro_verify",
                        conditions=[RefExistsCondition(type="ref_exists", ref="upload_btn")],
                    ),
                ],
            )
        },
        steps=[
            FindTextStep(
                type="find_text",
                id="find_upload",
                query="${button_label}",
                strategy="uia_or_ocr",
                save_as="upload_btn",
            ),
            ClickRefStep(type="click_ref", id="click_upload", ref="upload_btn"),
            CallSubmacroStep(type="call_submacro", id="call_submit", submacro="submit"),
            VerifyAllStep(
                type="verify_all",
                id="verify_end",
                conditions=[
                    RefExistsCondition(type="ref_exists", ref="upload_btn"),
                    StepSucceededCondition(type="step_succeeded", step_id="call_submit"),
                ],
            ),
        ],
    )
    ctx = make_context(macro)
    runner = MacroRunner()

    result = runner.run(macro, ctx)

    assert result.status == StepStatus.SUCCESS
    assert "upload_btn" in ctx.references
    assert ctx.references["upload_btn"].text == "업로드"
    assert ctx.step_outcomes["call_submit"] is True
    assert ctx.input_controller.calls == []
