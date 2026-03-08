from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

from aiautomouse.engine.models import DomLocatorSpec, TargetSpec
from aiautomouse.engine.results import ActionExecutionError, Rect, TargetMatch


@dataclass
class BrowserPageCandidate:
    page: Any
    context_index: int
    page_index: int


class PlaywrightBrowserAdapter:
    def __init__(
        self,
        *,
        cdp_url: str | None = "http://127.0.0.1:9222",
        launch_on_demand: bool = True,
        channel: str | None = "msedge",
        headless: bool = False,
        default_timeout_ms: int = 5000,
        connect_timeout_ms: int = 1500,
        sync_playwright_factory: Callable[[], Any] | None = None,
        urlopen_fn: Callable[..., Any] = urlopen,
    ) -> None:
        self.cdp_url = (cdp_url or "").rstrip("/")
        self.launch_on_demand = launch_on_demand
        self.channel = channel
        self.headless = headless
        self.default_timeout_ms = max(1, default_timeout_ms)
        self.connect_timeout_ms = max(1, connect_timeout_ms)
        self._sync_playwright_factory = sync_playwright_factory
        self._urlopen = urlopen_fn
        self._playwright_manager = None
        self._playwright = None
        self._browser = None
        self._session_mode = "uninitialized"
        self._active_page_key: str | None = None

    def is_available(self) -> bool:
        if not self._can_import_playwright():
            return False
        if self._cdp_is_available():
            return True
        return self.launch_on_demand

    def close(self) -> None:
        with contextlib.suppress(Exception):
            if self._browser is not None:
                self._browser.close()
        self._browser = None
        with contextlib.suppress(Exception):
            if self._playwright_manager is not None:
                self._playwright_manager.stop()
        self._playwright_manager = None
        self._playwright = None
        self._active_page_key = None

    def open_page(
        self,
        *,
        url: str,
        new_tab: bool = True,
        new_window: bool = False,
        reuse_existing: bool = False,
        title_contains: str | None = None,
        url_contains: str | None = None,
        wait_until: str = "load",
        ctx: object | None = None,
    ) -> dict[str, Any]:
        self._ensure_browser()
        page = None
        if reuse_existing:
            page = self._find_existing_page(title_contains=title_contains, url_contains=url_contains or url)
        if page is None:
            page = self._create_page(new_tab=new_tab, new_window=new_window)
        page.goto(url, wait_until=wait_until, timeout=self.default_timeout_ms)
        page.bring_to_front()
        candidate = self._candidate_for_page(page)
        if candidate is None:
            raise ActionExecutionError("Failed to track browser page after navigation")
        title = self._safe_page_title(page)
        details = {
            "url": page.url,
            "title": title,
            "context_index": candidate.context_index,
            "page_index": candidate.page_index,
            "page_key": self._page_key(candidate.context_index, candidate.page_index),
            "session_mode": self._session_mode,
        }
        self._remember_active_page(candidate, ctx)
        return details

    def find_target(self, target: TargetSpec, ctx: object | None = None) -> TargetMatch | None:
        dom = target.dom
        if dom is None:
            return None
        candidates = self._iter_candidate_pages(dom, target.window)
        for candidate in candidates:
            try:
                match = self._locate_on_candidate(candidate, dom, ctx)
            except Exception as exc:
                self._record_error(ctx, "find_target", exc, candidate.page, dom)
                continue
            if match is not None:
                self._remember_active_page(candidate, ctx)
                return match
        if ctx is not None and getattr(ctx, "is_dry_run", False):
            dry_run_page = ctx.state.get("browser_active_page") or {}
            if dry_run_page.get("dry_run"):
                return TargetMatch(
                    provider_name="browser_cdp",
                    rect=Rect(0, 0, 1, 1),
                    confidence=0.0,
                    text=dom.text or dom.name or dom.label,
                    metadata={
                        "interaction_mode": "browser",
                        "dom": dom.model_dump(exclude_none=True, mode="python"),
                        "page_key": str(dry_run_page.get("page_key") or "dry-run:0"),
                        "page_title": str(dry_run_page.get("title") or ""),
                        "url": str(dry_run_page.get("url") or ""),
                        "session_mode": "dry-run",
                        "locator": self._locator_summary(dom),
                        "dry_run_placeholder": True,
                    },
                )
        return None

    def click_match(
        self,
        match: TargetMatch,
        *,
        button: str = "left",
        double: bool = False,
        ctx: object | None = None,
    ) -> dict[str, Any]:
        page, locator, candidate, dom = self._resolve_live_locator(match)
        page.bring_to_front()
        if double:
            locator.dblclick(button=button, timeout=self._timeout_for_dom(dom))
        else:
            locator.click(button=button, timeout=self._timeout_for_dom(dom))
        self._remember_active_page(candidate, ctx)
        return {
            "provider": "browser_cdp",
            "button": button,
            "double": double,
            "page_key": self._page_key(candidate.context_index, candidate.page_index),
            "url": page.url,
        }

    def type_text(self, text: str, *, match: TargetMatch | None = None, ctx: object | None = None) -> dict[str, Any]:
        page, locator, candidate, dom = self._resolve_action_target(match)
        if locator is not None:
            locator.click(timeout=self._timeout_for_dom(dom))
        page.keyboard.type(text)
        if candidate is not None:
            self._remember_active_page(candidate, ctx)
        return {"provider": "browser_cdp", "text": text, "page_url": page.url}

    def paste_text(self, text: str, *, match: TargetMatch | None = None, ctx: object | None = None) -> dict[str, Any]:
        page, locator, candidate, dom = self._resolve_action_target(match)
        if locator is not None:
            locator.click(timeout=self._timeout_for_dom(dom))
        page.keyboard.insert_text(text)
        if candidate is not None:
            self._remember_active_page(candidate, ctx)
        return {"provider": "browser_cdp", "text": text, "page_url": page.url}

    def press_keys(self, chords: list[list[str]], *, ctx: object | None = None) -> dict[str, Any]:
        candidate = self._current_candidate()
        if candidate is None:
            raise ActionExecutionError("No active browser page for browser key press")
        candidate.page.bring_to_front()
        for chord in chords:
            candidate.page.keyboard.press("+".join(self._normalize_key(token) for token in chord))
        self._remember_active_page(candidate, ctx)
        return {"provider": "browser_cdp", "keys": chords, "page_url": candidate.page.url}

    def upload_files(
        self,
        files: str | list[str],
        *,
        match: TargetMatch,
        allow_file_chooser: bool = True,
        ctx: object | None = None,
    ) -> dict[str, Any]:
        paths = [str(Path(path).expanduser().resolve()) for path in ([files] if isinstance(files, str) else files)]
        page, locator, candidate, dom = self._resolve_live_locator(match)
        timeout = self._timeout_for_dom(dom)
        if self._is_file_input(locator):
            locator.set_input_files(paths, timeout=timeout)
            mode = "direct_input"
        elif allow_file_chooser:
            with page.expect_file_chooser(timeout=timeout) as chooser_info:
                locator.click(timeout=timeout)
            chooser_info.value.set_files(paths)
            mode = "file_chooser"
        else:
            raise ActionExecutionError("Target is not a file input and file chooser fallback is disabled")
        self._remember_active_page(candidate, ctx)
        return {"provider": "browser_cdp", "files": paths, "mode": mode, "page_url": page.url}

    def has_active_page(self) -> bool:
        return self._current_candidate() is not None

    def _resolve_action_target(self, match: TargetMatch | None) -> tuple[Any, Any | None, BrowserPageCandidate | None, DomLocatorSpec | None]:
        if match is not None:
            page, locator, candidate, dom = self._resolve_live_locator(match)
            return page, locator, candidate, dom
        candidate = self._current_candidate()
        if candidate is None:
            raise ActionExecutionError("No active browser page")
        return candidate.page, None, candidate, None

    def _resolve_live_locator(self, match: TargetMatch) -> tuple[Any, Any, BrowserPageCandidate, DomLocatorSpec]:
        dom_payload = match.metadata.get("dom")
        if not isinstance(dom_payload, dict):
            raise ActionExecutionError("Browser target match is missing DOM locator metadata")
        dom = DomLocatorSpec.model_validate(dom_payload)
        candidate = self._candidate_from_page_key(match.metadata.get("page_key"))
        if candidate is None:
            candidates = self._iter_candidate_pages(dom, None)
            candidate = candidates[0] if candidates else None
        if candidate is None:
            raise ActionExecutionError("Browser page is no longer available")
        locator = self._build_locator(candidate.page, dom)
        locator = locator.nth(dom.nth)
        self._apply_waits(candidate.page, locator, dom)
        return candidate.page, locator, candidate, dom

    def _locate_on_candidate(
        self,
        candidate: BrowserPageCandidate,
        dom: DomLocatorSpec,
        ctx: object | None,
    ) -> TargetMatch | None:
        page = candidate.page
        locator = self._build_locator(page, dom)
        locator = locator.nth(dom.nth)
        self._apply_waits(page, locator, dom)
        with contextlib.suppress(Exception):
            locator.scroll_into_view_if_needed(timeout=self._timeout_for_dom(dom))
        box = locator.bounding_box()
        if not box:
            return None
        rect = self._box_to_rect(page, box)
        title = self._safe_page_title(page)
        text = self._safe_element_text(locator)
        input_type = self._safe_eval(
            locator,
            "(element) => element instanceof HTMLInputElement ? element.type : null",
        )
        tag_name = self._safe_eval(locator, "(element) => element.tagName ? element.tagName.toLowerCase() : null")
        metadata = {
            "interaction_mode": "browser",
            "dom": dom.model_dump(exclude_none=True, mode="python"),
            "page_key": self._page_key(candidate.context_index, candidate.page_index),
            "page_title": title,
            "url": page.url,
            "session_mode": self._session_mode,
            "locator": self._locator_summary(dom),
            "input_type": input_type,
            "tag_name": tag_name,
        }
        return TargetMatch(
            provider_name="browser_cdp",
            rect=rect,
            confidence=1.0,
            text=text,
            metadata=metadata,
        )

    def _iter_candidate_pages(self, dom: DomLocatorSpec, window: Any | None) -> list[BrowserPageCandidate]:
        try:
            browser = self._ensure_browser()
        except Exception:
            return []
        candidates: list[BrowserPageCandidate] = []
        for context_index, browser_context in enumerate(browser.contexts):
            if dom.context_index is not None and context_index != dom.context_index:
                continue
            for page_index, page in enumerate(browser_context.pages):
                if dom.page_index is not None and page_index != dom.page_index:
                    continue
                title = self._safe_page_title(page)
                if dom.title_contains and dom.title_contains.lower() not in title.lower():
                    continue
                if dom.url_contains and dom.url_contains.lower() not in str(page.url).lower():
                    continue
                if window is not None and window.title_contains:
                    if window.title_contains.lower() not in title.lower():
                        continue
                candidates.append(BrowserPageCandidate(page=page, context_index=context_index, page_index=page_index))
        active_key = self._active_page_key
        candidates.sort(key=lambda item: 0 if self._page_key(item.context_index, item.page_index) == active_key else 1)
        return candidates

    def _find_existing_page(self, *, title_contains: str | None = None, url_contains: str | None = None):
        for candidate in self._iter_candidate_pages(
            DomLocatorSpec(text="body", title_contains=title_contains, url_contains=url_contains),
            None,
        ):
            return candidate.page
        return None

    def _create_page(self, *, new_tab: bool, new_window: bool):
        browser = self._ensure_browser()
        active = self._current_candidate()
        if new_window or not browser.contexts:
            context = browser.new_context(no_viewport=True)
            return context.new_page()
        if new_tab:
            context = active.page.context if active is not None else browser.contexts[0]
            return context.new_page()
        if active is not None:
            return active.page
        if browser.contexts[0].pages:
            return browser.contexts[0].pages[0]
        return browser.contexts[0].new_page()

    def _current_candidate(self) -> BrowserPageCandidate | None:
        return self._candidate_from_page_key(self._active_page_key)

    def _candidate_for_page(self, page: Any) -> BrowserPageCandidate | None:
        browser = self._ensure_browser()
        for context_index, browser_context in enumerate(browser.contexts):
            for page_index, candidate_page in enumerate(browser_context.pages):
                if candidate_page is page:
                    return BrowserPageCandidate(page=page, context_index=context_index, page_index=page_index)
        return None

    def _candidate_from_page_key(self, page_key: Any) -> BrowserPageCandidate | None:
        if not isinstance(page_key, str) or ":" not in page_key:
            return None
        try:
            context_index, page_index = (int(part) for part in page_key.split(":", 1))
        except ValueError:
            return None
        browser = self._ensure_browser()
        if context_index >= len(browser.contexts):
            return None
        context = browser.contexts[context_index]
        if page_index >= len(context.pages):
            return None
        return BrowserPageCandidate(page=context.pages[page_index], context_index=context_index, page_index=page_index)

    def _apply_waits(self, page: Any, locator: Any, dom: DomLocatorSpec) -> None:
        timeout = self._timeout_for_dom(dom)
        if dom.wait_for_network_idle:
            page.wait_for_load_state("networkidle", timeout=timeout)
        locator.wait_for(state=dom.wait_for, timeout=timeout)
        if dom.require_enabled:
            self._wait_for_enabled(locator, timeout)
        if dom.require_stable:
            self._wait_for_stable(locator, timeout)

    def _wait_for_enabled(self, locator: Any, timeout_ms: int) -> None:
        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        while time.perf_counter() <= deadline:
            if locator.is_enabled():
                return
            time.sleep(0.05)
        raise ActionExecutionError("Browser locator did not become enabled before timeout")

    def _wait_for_stable(self, locator: Any, timeout_ms: int) -> None:
        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        previous_box = None
        stable_count = 0
        while time.perf_counter() <= deadline:
            box = locator.bounding_box()
            if box and box == previous_box:
                stable_count += 1
                if stable_count >= 2:
                    return
            else:
                stable_count = 0
            previous_box = box
            time.sleep(0.05)
        raise ActionExecutionError("Browser locator did not become stable before timeout")

    def _build_locator(self, page: Any, dom: DomLocatorSpec):
        locator = None
        if dom.role:
            locator = page.get_by_role(dom.role, name=dom.name or dom.text)
        elif dom.label:
            locator = page.get_by_label(dom.label)
        elif dom.placeholder:
            locator = page.get_by_placeholder(dom.placeholder)
        elif dom.test_id:
            locator = page.get_by_test_id(dom.test_id)
        elif dom.xpath:
            locator = page.locator(f"xpath={dom.xpath}")
        elif dom.selector or dom.css:
            locator = page.locator(dom.selector or dom.css)
        elif dom.text:
            locator = page.get_by_text(dom.text)
        if locator is None:
            raise ActionExecutionError("Unsupported DOM locator")
        if dom.text and any((dom.role, dom.selector, dom.css, dom.xpath, dom.label, dom.placeholder, dom.test_id)):
            with contextlib.suppress(Exception):
                locator = locator.filter(has_text=dom.text)
        return locator

    def _box_to_rect(self, page: Any, box: dict[str, float]) -> Rect:
        metrics = page.evaluate(
            """
            () => ({
              screenX: window.screenX,
              screenY: window.screenY,
              outerWidth: window.outerWidth,
              outerHeight: window.outerHeight,
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              devicePixelRatio: window.devicePixelRatio || 1
            })
            """
        )
        frame_x = max(0.0, (metrics["outerWidth"] - metrics["innerWidth"]) / 2.0)
        frame_y = max(0.0, metrics["outerHeight"] - metrics["innerHeight"] - frame_x)
        scale = float(metrics.get("devicePixelRatio") or 1.0)
        return Rect(
            left=int(round((metrics["screenX"] + frame_x + box["x"]) * scale)),
            top=int(round((metrics["screenY"] + frame_y + box["y"]) * scale)),
            width=max(1, int(round(box["width"] * scale))),
            height=max(1, int(round(box["height"] * scale))),
        )

    def _timeout_for_dom(self, dom: DomLocatorSpec | None) -> int:
        if dom is None or dom.timeout_ms is None:
            return self.default_timeout_ms
        return dom.timeout_ms

    def _normalize_key(self, key: str) -> str:
        mapping = {
            "CTRL": "Control",
            "CONTROL": "Control",
            "ALT": "Alt",
            "SHIFT": "Shift",
            "WIN": "Meta",
            "META": "Meta",
            "ENTER": "Enter",
            "ESC": "Escape",
            "ESCAPE": "Escape",
            "TAB": "Tab",
            "SPACE": "Space",
            "PGUP": "PageUp",
            "PGDN": "PageDown",
            "UP": "ArrowUp",
            "DOWN": "ArrowDown",
            "LEFT": "ArrowLeft",
            "RIGHT": "ArrowRight",
        }
        token = str(key).strip()
        return mapping.get(token.upper(), token.title() if len(token) > 1 else token)

    def _is_file_input(self, locator: Any) -> bool:
        result = self._safe_eval(
            locator,
            "(element) => element instanceof HTMLInputElement && element.type === 'file'",
        )
        return bool(result)

    def _safe_page_title(self, page: Any) -> str:
        with contextlib.suppress(Exception):
            return str(page.title())
        return ""

    def _safe_element_text(self, locator: Any) -> str | None:
        for method_name in ("inner_text", "text_content"):
            method = getattr(locator, method_name, None)
            if method is None:
                continue
            with contextlib.suppress(Exception):
                value = method(timeout=self.default_timeout_ms) if method_name == "inner_text" else method()
                if value is not None:
                    return str(value).strip()
        return None

    def _safe_eval(self, locator: Any, script: str) -> Any:
        with contextlib.suppress(Exception):
            return locator.evaluate(script)
        return None

    def _record_error(self, ctx: object | None, phase: str, error: Exception, page: Any, dom: DomLocatorSpec) -> None:
        if ctx is not None and hasattr(ctx, "event_logger"):
            ctx.event_logger.emit(
                "browser_error",
                phase=phase,
                error=str(error),
                locator=self._locator_summary(dom),
                page_url=getattr(page, "url", ""),
                page_title=self._safe_page_title(page),
            )
        if ctx is not None and hasattr(ctx, "artifacts"):
            index = int(ctx.state.get("browser_error_count", 0)) + 1
            ctx.state["browser_error_count"] = index
            debug_path = ctx.artifacts.debug_path("browser", f"{index:03d}_{phase}.json")
            payload = {
                "phase": phase,
                "error": str(error),
                "locator": self._locator_summary(dom),
                "page_url": str(getattr(page, "url", "")),
                "page_title": self._safe_page_title(page),
            }
            debug_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            screenshot_path = ctx.artifacts.debug_path("browser", f"{index:03d}_{phase}.png")
            with contextlib.suppress(Exception):
                page.screenshot(path=str(screenshot_path))

    def _locator_summary(self, dom: DomLocatorSpec) -> str:
        parts = [
            f"role={dom.role}" if dom.role else None,
            f"name={dom.name}" if dom.name else None,
            f"css={dom.css}" if dom.css else None,
            f"selector={dom.selector}" if dom.selector else None,
            f"xpath={dom.xpath}" if dom.xpath else None,
            f"text={dom.text}" if dom.text else None,
            f"title_contains={dom.title_contains}" if dom.title_contains else None,
            f"url_contains={dom.url_contains}" if dom.url_contains else None,
        ]
        return ", ".join(part for part in parts if part)

    def _remember_active_page(self, candidate: BrowserPageCandidate, ctx: object | None) -> None:
        self._active_page_key = self._page_key(candidate.context_index, candidate.page_index)
        if ctx is None:
            return
        title = self._safe_page_title(candidate.page)
        ctx.state["browser_active_page"] = {
            "context_index": candidate.context_index,
            "page_index": candidate.page_index,
            "page_key": self._active_page_key,
            "title": title,
            "url": candidate.page.url,
            "session_mode": self._session_mode,
        }

    def _page_key(self, context_index: int, page_index: int) -> str:
        return f"{context_index}:{page_index}"

    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        if not self._can_import_playwright():
            raise ActionExecutionError("Playwright is not installed")
        if self._sync_playwright_factory is None:
            from playwright.sync_api import sync_playwright

            self._sync_playwright_factory = sync_playwright
        if self._playwright_manager is None:
            self._playwright_manager = self._sync_playwright_factory().start()
            self._playwright = self._playwright_manager
        if self._cdp_is_available():
            self._browser = self._playwright.chromium.connect_over_cdp(
                self.cdp_url,
                timeout=self.connect_timeout_ms,
            )
            self._session_mode = "cdp"
            return self._browser
        if not self.launch_on_demand:
            raise ActionExecutionError("Chromium/Edge browser endpoint is unavailable")
        launch_kwargs: dict[str, Any] = {"headless": self.headless}
        if self.channel and self.channel.lower() != "chromium":
            launch_kwargs["channel"] = self.channel
        self._browser = self._playwright.chromium.launch(**launch_kwargs)
        self._session_mode = "launch"
        return self._browser

    def _can_import_playwright(self) -> bool:
        if self._sync_playwright_factory is not None:
            return True
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except Exception:
            return False
        return True

    def _cdp_is_available(self) -> bool:
        if not self.cdp_url:
            return False
        try:
            with self._urlopen(f"{self.cdp_url}/json/version", timeout=max(1, self.connect_timeout_ms / 1000.0)):
                return True
        except (OSError, URLError):
            return False
