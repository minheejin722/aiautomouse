from __future__ import annotations

from types import SimpleNamespace

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.browser.adapter import PlaywrightBrowserAdapter
from aiautomouse.engine.actions import ActionExecutor
from aiautomouse.engine.context import RunMode, RuntimeContext
from aiautomouse.engine.models import MacroSpec, TargetSpec
from aiautomouse.engine.results import Rect, TargetMatch
from aiautomouse.providers.browser_cdp import BrowserCdpProvider
from aiautomouse.engine.resolver import TargetResolver


class FakeArtifacts:
    def write_json(self, name, payload):
        return name

    def capture_failure_screenshot(self, step_id, screen_capture):
        return None

    def capture_named_screenshot(self, name, screen_capture):
        return None

    def debug_path(self, *parts):
        return SimpleNamespace(write_text=lambda *args, **kwargs: None)


class FakeLogger:
    def emit(self, event_type, **payload):
        return {"event": event_type, **payload}


class FakeOverlay:
    def show_target(self, match, label="", status="planned"):
        return None


class FakeStopToken:
    def is_set(self):
        return False


class FakeWindowManager:
    def get_active_window_info(self):
        return {"title": "Chromium", "class_name": "Chrome_WidgetWin_1"}

    def get_active_window_title(self):
        return "Chromium"


class FakeCapture:
    pass


class FakeSnippets:
    def get(self, name):
        return f"snippet:{name}"


class FakeTemplates:
    def resolve(self, reference):
        return reference


class RecordingDesktopInput:
    def __init__(self):
        self.calls = []

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))

    def double_click(self, *args, **kwargs):
        self.calls.append(("double_click", args, kwargs))

    def type_text(self, *args, **kwargs):
        self.calls.append(("type_text", args, kwargs))

    def paste_text(self, *args, **kwargs):
        self.calls.append(("paste_text", args, kwargs))

    def hotkey(self, *args, **kwargs):
        self.calls.append(("hotkey", args, kwargs))

    def get_clipboard_text(self):
        return "before"


class RecordingBrowserRuntime:
    def __init__(self):
        self.calls = []

    def has_active_page(self):
        return True

    def click_match(self, match, *, button="left", double=False, ctx=None):
        self.calls.append(("click_match", button, double, match.metadata.get("page_key")))
        return {"provider": "browser_cdp", "button": button, "double": double}

    def type_text(self, text, *, match=None, ctx=None):
        self.calls.append(("type_text", text, match.metadata.get("page_key") if match else None))
        return {"provider": "browser_cdp", "text": text}

    def paste_text(self, text, *, match=None, ctx=None):
        self.calls.append(("paste_text", text, match.metadata.get("page_key") if match else None))
        return {"provider": "browser_cdp", "text": text}

    def press_keys(self, chords, *, ctx=None):
        self.calls.append(("press_keys", chords))
        return {"provider": "browser_cdp", "keys": chords}


class FakeKeyboard:
    def __init__(self):
        self.calls = []

    def type(self, text):
        self.calls.append(("type", text))

    def insert_text(self, text):
        self.calls.append(("insert_text", text))

    def press(self, key):
        self.calls.append(("press", key))


class FakeFileChooser:
    def __init__(self):
        self.files = None

    def set_files(self, files):
        self.files = files


class FakeFileChooserContext:
    def __init__(self, chooser):
        self.value = chooser

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeLocator:
    def __init__(self, *, text="Upload", input_type="button", tag_name="button", file_input=False):
        self.text = text
        self.input_type = input_type
        self.tag_name = tag_name
        self.file_input = file_input
        self.filtered_by = None
        self.actions = []
        self.paths = None

    def nth(self, index):
        self.actions.append(("nth", index))
        return self

    def wait_for(self, *, state, timeout):
        self.actions.append(("wait_for", state, timeout))

    def is_enabled(self):
        return True

    def bounding_box(self):
        return {"x": 20, "y": 30, "width": 100, "height": 40}

    def inner_text(self, timeout=None):
        return self.text

    def text_content(self):
        return self.text

    def evaluate(self, script):
        if "type === 'file'" in script:
            return self.file_input
        if "HTMLInputElement ? element.type" in script:
            return self.input_type
        if "tagName" in script:
            return self.tag_name
        return None

    def filter(self, *, has_text):
        self.filtered_by = has_text
        return self

    def scroll_into_view_if_needed(self, timeout=None):
        self.actions.append(("scroll", timeout))

    def click(self, *, button="left", timeout=None):
        self.actions.append(("click", button, timeout))

    def dblclick(self, *, button="left", timeout=None):
        self.actions.append(("dblclick", button, timeout))

    def set_input_files(self, paths, timeout=None):
        self.paths = list(paths)
        self.actions.append(("set_input_files", list(paths), timeout))


class FakePage:
    def __init__(self, locator):
        self._locator = locator
        self.url = "https://example.test/upload"
        self.keyboard = FakeKeyboard()
        self.chooser = FakeFileChooser()
        self.calls = []
        self.context = None

    def title(self):
        return "Upload - Chromium"

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", role, name))
        return self._locator

    def get_by_text(self, text):
        self.calls.append(("get_by_text", text))
        return self._locator

    def get_by_label(self, label):
        self.calls.append(("get_by_label", label))
        return self._locator

    def get_by_placeholder(self, placeholder):
        self.calls.append(("get_by_placeholder", placeholder))
        return self._locator

    def get_by_test_id(self, test_id):
        self.calls.append(("get_by_test_id", test_id))
        return self._locator

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return self._locator

    def evaluate(self, script):
        if "screenX" in script:
            return {
                "screenX": 100,
                "screenY": 200,
                "outerWidth": 1400,
                "outerHeight": 900,
                "innerWidth": 1360,
                "innerHeight": 820,
                "devicePixelRatio": 1.5,
            }
        return None

    def wait_for_load_state(self, state, timeout):
        self.calls.append(("wait_for_load_state", state, timeout))

    def bring_to_front(self):
        self.calls.append(("bring_to_front",))

    def goto(self, url, wait_until, timeout):
        self.url = url
        self.calls.append(("goto", url, wait_until, timeout))

    def expect_file_chooser(self, timeout):
        self.calls.append(("expect_file_chooser", timeout))
        return FakeFileChooserContext(self.chooser)

    def screenshot(self, path):
        self.calls.append(("screenshot", path))


class FakeBrowserContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        for page in self.pages:
            page.context = self

    def new_page(self):
        page = FakePage(FakeLocator())
        page.context = self
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self, contexts=None):
        self.contexts = list(contexts or [])

    def new_context(self, no_viewport=True):
        context = FakeBrowserContext()
        self.contexts.append(context)
        return context

    def close(self):
        return None


class StaticBrowserAdapter(PlaywrightBrowserAdapter):
    def __init__(self, browser):
        super().__init__(cdp_url=None, launch_on_demand=False)
        self._static_browser = browser
        self._session_mode = "test"

    def _ensure_browser(self):
        return self._static_browser

    def is_available(self):
        return True


def make_context(*, browser=None, resolver=None):
    macro = MacroSpec(name="browser_macro", steps=[])
    return RuntimeContext(
        settings=AppSettings.from_dict({"poll_interval_ms": 0}),
        mode=RunMode.EXECUTE,
        resolver=resolver or SimpleNamespace(resolve=lambda target, ctx: target),
        artifacts=FakeArtifacts(),
        event_logger=FakeLogger(),
        overlay=FakeOverlay(),
        stop_token=FakeStopToken(),
        input_controller=RecordingDesktopInput(),
        window_manager=FakeWindowManager(),
        screen_capture=FakeCapture(),
        snippets=FakeSnippets(),
        templates=FakeTemplates(),
        macro_path="macro.yaml",
        macro=macro,
        browser=browser,
    )


def make_dry_run_context(*, browser=None):
    ctx = make_context(browser=browser)
    ctx.mode = RunMode.DRY_RUN
    return ctx


def browser_match():
    return TargetMatch(
        "browser_cdp",
        Rect(10, 20, 30, 40),
        1.0,
        text="Upload",
        metadata={
            "interaction_mode": "browser",
            "page_key": "0:0",
            "dom": {"role": "button", "name": "Upload"},
        },
    )


def test_browser_adapter_returns_browser_target_for_role_locator():
    locator = FakeLocator(text="Upload")
    page = FakePage(locator)
    browser = FakeBrowser([FakeBrowserContext([page])])
    adapter = StaticBrowserAdapter(browser)

    match = adapter.find_target(TargetSpec(dom={"role": "button", "name": "Upload"}))

    assert match is not None
    assert match.provider_name == "browser_cdp"
    assert match.metadata["interaction_mode"] == "browser"
    assert match.metadata["page_key"] == "0:0"
    assert page.calls[0] == ("get_by_role", "button", "Upload")
    assert match.rect.left == 210
    assert match.rect.top == 435


def test_upload_files_prefers_direct_file_input():
    locator = FakeLocator(text="Upload", input_type="file", tag_name="input", file_input=True)
    page = FakePage(locator)
    browser = FakeBrowser([FakeBrowserContext([page])])
    adapter = StaticBrowserAdapter(browser)
    match = adapter.find_target(TargetSpec(dom={"css": "input[type='file']"}))

    result = adapter.upload_files(["tests/data/sample.txt"], match=match)

    assert result["mode"] == "direct_input"
    assert locator.paths and locator.paths[0].endswith("tests\\data\\sample.txt")
    assert not any(call[0] == "expect_file_chooser" for call in page.calls)


def test_upload_files_uses_file_chooser_when_not_file_input():
    locator = FakeLocator(text="Upload", input_type="button", tag_name="button", file_input=False)
    page = FakePage(locator)
    browser = FakeBrowser([FakeBrowserContext([page])])
    adapter = StaticBrowserAdapter(browser)
    match = adapter.find_target(TargetSpec(dom={"role": "button", "name": "Upload"}))

    result = adapter.upload_files(["tests/data/sample.txt"], match=match)

    assert result["mode"] == "file_chooser"
    assert page.chooser.files and page.chooser.files[0].endswith("tests\\data\\sample.txt")
    assert any(call[0] == "expect_file_chooser" for call in page.calls)


def test_action_executor_routes_browser_refs_to_browser_runtime():
    runtime = RecordingBrowserRuntime()
    ctx = make_context(browser=runtime)
    executor = ActionExecutor()
    ctx.references["upload"] = browser_match()

    executor.click_ref("upload", ctx)
    executor.type_text("hello", ctx, ref="upload")
    executor.paste_snippet("prompt_01", ctx, ref="upload")
    executor.press_keys("ctrl+enter", ctx)

    assert ctx.input_controller.calls == []
    assert runtime.calls == [
        ("click_match", "left", False, "0:0"),
        ("type_text", "hello", "0:0"),
        ("paste_text", "snippet:prompt_01", "0:0"),
        ("press_keys", [["CTRL", "ENTER"]]),
    ]


def test_browser_adapter_returns_synthetic_target_for_dry_run_open_page():
    adapter = StaticBrowserAdapter(FakeBrowser([FakeBrowserContext([])]))
    ctx = make_dry_run_context(browser=adapter)
    ActionExecutor().open_page(ctx, url="https://example.test", new_window=True)

    match = adapter.find_target(TargetSpec(dom={"text": "Upload"}), ctx)

    assert match is not None
    assert match.metadata["dry_run_placeholder"] is True
    assert match.metadata["page_key"] == "dry-run:0"


def test_resolver_falls_back_after_browser_provider_miss():
    browser = FakeBrowser([FakeBrowserContext([])])
    browser_provider = BrowserCdpProvider(StaticBrowserAdapter(browser))
    fallback = SimpleNamespace(
        name="windows_uia",
        supports=lambda target: True,
        is_available=lambda: True,
        find=lambda target, ctx: TargetMatch("windows_uia", Rect(1, 2, 3, 4), 1.0),
    )
    resolver = TargetResolver([browser_provider, fallback])

    match = resolver.resolve(TargetSpec(dom={"text": "Upload"}, uia={"name_contains": "Upload"}), ctx=object())

    assert match.provider_name == "windows_uia"
