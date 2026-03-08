from __future__ import annotations

import subprocess
from typing import Any

from aiautomouse.engine.models import LegacyActionSpec, OffsetSpec, TargetSpec, WindowLocatorSpec
from aiautomouse.engine.results import ActionExecutionError, TargetMatch


class ActionExecutor:
    def open_page(
        self,
        ctx: object,
        *,
        url: str,
        new_tab: bool = True,
        new_window: bool = False,
        reuse_existing: bool = False,
        title_contains: str | None = None,
        url_contains: str | None = None,
        wait_until: str = "load",
    ) -> dict[str, Any]:
        if ctx.browser is None:
            raise ActionExecutionError("Browser automation is not configured")
        if ctx.is_dry_run:
            details = {
                "url": url,
                "new_tab": new_tab,
                "new_window": new_window,
                "reuse_existing": reuse_existing,
                "wait_until": wait_until,
                "mode": "dry-run",
            }
            ctx.state["browser_active_page"] = {
                "page_key": "dry-run:0",
                "url": url,
                "title": title_contains or url_contains or "dry-run",
                "session_mode": "dry-run",
                "dry_run": True,
            }
            return details
        details = ctx.browser.open_page(
            url=url,
            new_tab=new_tab,
            new_window=new_window,
            reuse_existing=reuse_existing,
            title_contains=title_contains,
            url_contains=url_contains,
            wait_until=wait_until,
            ctx=ctx,
        )
        ctx.refresh_active_window()
        return details

    def focus_window(
        self,
        ctx: object,
        *,
        title: str | None = None,
        title_contains: str | None = None,
        class_name: str | None = None,
        anchor: str | None = None,
    ) -> dict[str, Any]:
        target = TargetSpec(anchor=anchor, window=WindowLocatorSpec.model_validate(
            {
                key: value
                for key, value in {
                    "title": title,
                    "title_contains": title_contains,
                    "class_name": class_name,
                }.items()
                if value is not None
            }
        ) if any((title, title_contains, class_name)) else None)
        resolved_target = ctx.resolve_target(target)
        window = resolved_target.window if resolved_target else None
        if window is None:
            raise ActionExecutionError("focus_window requires a window locator")
        if ctx.is_dry_run:
            found = ctx.window_manager.find_window(
                title=window.title,
                title_contains=window.title_contains,
                class_name=window.class_name,
            )
            if found is None:
                raise ActionExecutionError("window not found")
            ctx.active_window_info = found.to_dict()
            return {"window": found.to_dict()}
        info = ctx.window_manager.focus_window(
            title=window.title,
            title_contains=window.title_contains,
            class_name=window.class_name,
        )
        if info is None:
            raise ActionExecutionError("window not found")
        ctx.refresh_active_window()
        return {"window": info}

    def resolve_target(self, target: TargetSpec, ctx: object, save_as: str | None = None, label: str = "") -> TargetMatch:
        resolved_target = ctx.resolve_target(target)
        match = ctx.resolver.resolve(resolved_target, ctx)
        ctx.overlay.show_target(match, label=label or "target", status="resolved")
        if save_as:
            ctx.remember_ref(save_as, match)
        return match

    def click_ref(
        self,
        ref: str,
        ctx: object,
        *,
        button: str = "left",
        double: bool = False,
        offset: OffsetSpec | list[int] | tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        match = ctx.get_ref(ref)
        ctx.overlay.show_target(match, label=f"{button}_click", status="planned")
        if self._is_browser_match(match):
            if ctx.is_dry_run:
                return {
                    "ref": ref,
                    "provider": match.provider_name,
                    "button": button,
                    "double": double,
                    "mode": "dry-run",
                }
            return ctx.browser.click_match(match, button=button, double=double, ctx=ctx)
        point = self._point_from_match(match, offset)
        if not ctx.is_dry_run:
            if double:
                ctx.input_controller.double_click(point[0], point[1], button=button)
            else:
                ctx.input_controller.click(point[0], point[1], button=button)
        return {"ref": ref, "point": point, "provider": match.provider_name, "button": button}

    def click_xy(self, x: int, y: int, ctx: object) -> dict[str, Any]:
        if not ctx.is_dry_run:
            ctx.input_controller.click(x, y, button="left")
        return {"point": (x, y)}

    def double_click_xy(self, x: int, y: int, ctx: object) -> dict[str, Any]:
        if not ctx.is_dry_run:
            ctx.input_controller.double_click(x, y, button="left")
        return {"point": (x, y)}

    def right_click_xy(self, x: int, y: int, ctx: object) -> dict[str, Any]:
        if not ctx.is_dry_run:
            ctx.input_controller.click(x, y, button="right")
        return {"point": (x, y)}

    def type_text(self, text: str, ctx: object, ref: str | None = None) -> dict[str, Any]:
        point = None
        browser_match = None
        if ref:
            match = ctx.get_ref(ref)
            ctx.overlay.show_target(match, label="type_text", status="planned")
            if self._is_browser_match(match):
                browser_match = match
            else:
                point = self._point_from_match(match, None)
                if not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button="left")
        elif ctx.browser is not None and ctx.browser.has_active_page():
            browser_match = None
        if browser_match is not None or (ref is None and ctx.browser is not None and ctx.browser.has_active_page()):
            if ctx.is_dry_run:
                return {"text": text, "point": point, "ref": ref, "provider": "browser_cdp", "mode": "dry-run"}
            return ctx.browser.type_text(text, match=browser_match, ctx=ctx)
        if not ctx.is_dry_run:
            ctx.input_controller.type_text(text)
        return {"text": text, "point": point, "ref": ref}

    def paste_snippet(self, snippet_id: str, ctx: object, ref: str | None = None) -> dict[str, Any]:
        text = ctx.snippets.get(snippet_id)
        point = None
        browser_match = None
        clipboard_before = None
        if hasattr(ctx.input_controller, "get_clipboard_text"):
            clipboard_before = ctx.input_controller.get_clipboard_text()
        if ref:
            match = ctx.get_ref(ref)
            ctx.overlay.show_target(match, label="paste_snippet", status="planned")
            if self._is_browser_match(match):
                browser_match = match
            else:
                point = self._point_from_match(match, None)
                if not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button="left")
        elif ctx.browser is not None and ctx.browser.has_active_page():
            browser_match = None
        if browser_match is not None or (ref is None and ctx.browser is not None and ctx.browser.has_active_page()):
            ctx.remember_clipboard(before=clipboard_before, after=text)
            if ctx.is_dry_run:
                return {
                    "snippet_id": snippet_id,
                    "text": text,
                    "point": point,
                    "ref": ref,
                    "provider": "browser_cdp",
                    "mode": "dry-run",
                }
            return ctx.browser.paste_text(text, match=browser_match, ctx=ctx)
        if not ctx.is_dry_run:
            ctx.input_controller.paste_text(text)
        ctx.remember_clipboard(before=clipboard_before, after=text)
        return {"snippet_id": snippet_id, "text": text, "point": point, "ref": ref}

    def press_keys(self, keys: str | list[str], ctx: object) -> dict[str, Any]:
        chords = self._parse_key_sequence(keys)
        if ctx.browser is not None and ctx.browser.has_active_page():
            if ctx.is_dry_run:
                return {"keys": chords, "provider": "browser_cdp", "mode": "dry-run"}
            return ctx.browser.press_keys(chords, ctx=ctx)
        if not ctx.is_dry_run:
            for chord in chords:
                ctx.input_controller.hotkey(chord)
        return {"keys": chords}

    def upload_files(
        self,
        files: str | list[str],
        ctx: object,
        *,
        ref: str | None = None,
        target: TargetSpec | None = None,
        allow_file_chooser: bool = True,
    ) -> dict[str, Any]:
        if ctx.browser is None:
            raise ActionExecutionError("Browser automation is not configured")
        match = None
        if ref:
            match = ctx.get_ref(ref)
        elif target is not None:
            save_as = "__upload_target__"
            match = self.resolve_target(target, ctx, save_as=save_as, label="upload_files")
        if match is None:
            raise ActionExecutionError("upload_files requires a resolved target")
        if not self._is_browser_match(match):
            raise ActionExecutionError("upload_files requires a browser DOM target")
        ctx.overlay.show_target(match, label="upload_files", status="planned")
        if ctx.is_dry_run:
            return {"files": files, "ref": ref, "provider": "browser_cdp", "mode": "dry-run"}
        return ctx.browser.upload_files(files, match=match, allow_file_chooser=allow_file_chooser, ctx=ctx)

    def capture_screenshot(self, name: str, ctx: object) -> dict[str, Any]:
        path = ctx.artifacts.capture_named_screenshot(name, ctx.screen_capture)
        ctx.remember_screenshot(str(path) if path else None)
        return {"path": str(path) if path else None}

    def launch_process(self, command: str | list[str], ctx: object) -> dict[str, Any]:
        if isinstance(command, str):
            command_list = [ctx.render_string(command)]
        else:
            command_list = [ctx.render_string(str(part)) for part in command]
        if not ctx.is_dry_run:
            subprocess.Popen(command_list)
        return {"command": command_list}

    def execute_legacy(self, action: LegacyActionSpec, ctx: object) -> dict[str, Any]:
        kind = action.kind.lower()
        if kind == "noop":
            return {"kind": kind}
        if kind == "wait":
            duration = action.duration_ms or int(action.input or 0)
            ctx.sleep(duration)
            return {"kind": kind, "duration_ms": duration}
        if kind == "launch_process":
            return self.launch_process(action.input, ctx)
        if kind == "screenshot":
            name = str(action.input or "manual")
            return self.capture_screenshot(name, ctx)
        if kind in {"move_mouse", "click", "double_click", "type_text", "paste_text", "hotkey"}:
            match = None
            point = None
            if action.target is not None:
                match = self.resolve_target(action.target, ctx, label=kind)
                point = self._point_from_match(match, action.offset)
            if kind == "move_mouse":
                if point is None:
                    raise ActionExecutionError("move_mouse requires a target")
                if not ctx.is_dry_run:
                    ctx.input_controller.move_mouse(point[0], point[1], duration_ms=action.duration_ms)
                return {"kind": kind, "point": point}
            if kind == "click":
                if point is None:
                    raise ActionExecutionError("click requires a target")
                if not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button=action.button)
                return {"kind": kind, "point": point}
            if kind == "double_click":
                if point is None:
                    raise ActionExecutionError("double_click requires a target")
                if not ctx.is_dry_run:
                    ctx.input_controller.double_click(point[0], point[1], button=action.button)
                return {"kind": kind, "point": point}
            if kind == "type_text":
                text = self._resolve_text_payload(action.input, ctx)
                if point is not None and not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button="left")
                if not ctx.is_dry_run:
                    ctx.input_controller.type_text(text)
                return {"kind": kind, "text": text, "point": point}
            if kind == "paste_text":
                text = ctx.snippets.get(action.snippet) if action.snippet else self._resolve_text_payload(action.input, ctx)
                if point is not None and not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button="left")
                if not ctx.is_dry_run:
                    ctx.input_controller.paste_text(text)
                ctx.remember_clipboard(after=text)
                return {"kind": kind, "text": text, "point": point}
            if kind == "hotkey":
                keys = self._parse_key_sequence(action.input)[0]
                if point is not None and not ctx.is_dry_run:
                    ctx.input_controller.click(point[0], point[1], button="left")
                if not ctx.is_dry_run:
                    ctx.input_controller.hotkey(keys)
                return {"kind": kind, "keys": keys, "point": point}
        raise ActionExecutionError(f"Unsupported legacy action kind: {action.kind}")

    def _point_from_match(
        self,
        match: TargetMatch,
        offset: OffsetSpec | list[int] | tuple[int, int] | None,
    ) -> tuple[int, int]:
        metadata_offset = OffsetSpec.from_any(match.metadata.get("click_offset"))
        normalized = OffsetSpec.from_any(offset)
        return match.rect.offset(metadata_offset.x + normalized.x, metadata_offset.y + normalized.y)

    def _parse_key_sequence(self, keys: str | list[str]) -> list[list[str]]:
        if isinstance(keys, list):
            return [[str(item).upper() for item in keys]]
        chords = []
        for chunk in str(keys).split(","):
            tokens = [token.strip().upper() for token in chunk.split("+") if token.strip()]
            if tokens:
                chords.append(tokens)
        if not chords:
            raise ActionExecutionError("keys must contain at least one token")
        return chords

    def _resolve_text_payload(self, value: Any, ctx: object) -> str:
        if value is None:
            raise ActionExecutionError("text action requires input")
        if isinstance(value, (str, int, float)):
            return ctx.render_string(str(value))
        raise ActionExecutionError("Unsupported text payload")

    def _is_browser_match(self, match: TargetMatch) -> bool:
        return str(match.metadata.get("interaction_mode") or "").lower() == "browser"
