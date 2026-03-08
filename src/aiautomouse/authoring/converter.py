from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from aiautomouse.authoring.models import (
    AdapterRecommendation,
    AmbiguityWarning,
    MacroAuthoringResult,
    RequiredResourceChecklistItem,
    SuggestedFallbackStrategy,
)
from aiautomouse.engine.loader import load_macro_from_data

KEYWORD_PRIORITY = {"browser": 0, "uia": 1, "ocr": 2, "image": 3}


@dataclass(frozen=True)
class DetectedAction:
    action_type: str
    start: int
    end: int
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class _ConversionState:
    source_text: str
    existing_snippets: set[str]
    existing_templates: set[str]
    warnings: list[AmbiguityWarning] = field(default_factory=list)
    fallbacks: list[SuggestedFallbackStrategy] = field(default_factory=list)
    required_resources: dict[tuple[str, str], RequiredResourceChecklistItem] = field(default_factory=dict)
    adapter_scores: dict[str, float] = field(default_factory=dict)
    adapter_reasons: dict[str, list[str]] = field(default_factory=dict)
    browser_context: bool = False
    desktop_window_context: bool = False


class NaturalLanguageMacroConverter:
    _FOCUS_WINDOW_PATTERNS = (
        re.compile(
            "\\ucc3d\\s*\\uc81c\\ubaa9\\uc5d0\\s*[\\\"']?(?P<title>[^\\\"',.\\n]+?)[\\\"']?\\s*(?:\\uc774|\\uac00)?\\s*\\ud3ec\\ud568\\ub41c?\\s*\\ucc3d(?:\\uc744|\\ub97c)?\\s*(?:\\ud65c\\uc131\\ud654|\\ud3ec\\ucee4\\uc2a4|\\uc9d1\\uc911)",
            re.IGNORECASE,
        ),
        re.compile(
            "activate\\s+(?:the\\s+)?window\\s+(?:whose\\s+title\\s+contains|with\\s+title\\s+containing)\\s*[\\\"']?(?P<title>[^\\\"',.\\n]+?)[\\\"']?(?:\\s|$)",
            re.IGNORECASE,
        ),
    )
    _OPEN_PAGE_PATTERN = re.compile(
        "(?:(?:\\ud398\\uc774\\uc9c0|page|url)\\s*)?(?P<url>(?:https?://|data:text/)[^\\s,]+)\\s*(?:\\uc744|\\ub97c)?\\s*(?:\\uc5f4(?:\\uace0|\\uc5b4)|open)",
        re.IGNORECASE,
    )
    _FIND_TEXT_PATTERN = re.compile(
        "(?P<scope>\\ud654\\uba74\\uc5d0\\uc11c|screen(?:\\uc5d0\\uc11c)?|\\ube0c\\ub77c\\uc6b0\\uc800\\uc5d0\\uc11c|browser(?:\\uc5d0\\uc11c)?|\\ud398\\uc774\\uc9c0\\uc5d0\\uc11c|page(?:\\uc5d0\\uc11c)?|\\ucc3d\\uc5d0\\uc11c|window(?:\\uc5d0\\uc11c)?)?\\s*"
        "[\\\"'](?P<query>[^\\\"']+)[\\\"']\\s*(?:\\ud14d\\uc2a4\\ud2b8|text)?(?:\\ub97c|\\uc744)?\\s*(?:\\ucc3e(?:\\uace0|\\uc740|\\uc544|\\uc544\\uc11c)?|\\uac80\\uc0c9(?:\\ud558\\uace0|\\ud55c)?|wait\\s*for)",
        re.IGNORECASE,
    )
    _FIND_IMAGE_PATTERN = re.compile(
        "(?P<kind>template|\\ud15c\\ud50c\\ub9bf|image|\\uc774\\ubbf8\\uc9c0|icon|\\uc544\\uc774\\ucf58)\\s*[\\\"']?(?P<template>[A-Za-z0-9_./\\\\:-]+)[\\\"']?\\s*(?:\\ub97c|\\uc744)?\\s*(?:\\ucc3e(?:\\uace0|\\uc740|\\uc544)?|\\uac80\\uc0c9(?:\\ud558\\uace0)?|wait\\s*for)",
        re.IGNORECASE,
    )
    _PASTE_SNIPPET_PATTERN = re.compile(
        "(?:snippet|\\uc2a4\\ub2c8\\ud3ab)\\s*[\\\"']?(?P<snippet>[A-Za-z0-9_.-]+)[\\\"']?(?:\\uc744|\\ub97c)?\\s*(?:\\ubd99\\uc5ec\\ub123(?:\\uace0|\\uae30|\\uc5b4)|paste)",
        re.IGNORECASE,
    )
    _TYPE_TEXT_PATTERN = re.compile(
        "[\\\"'](?P<text>[^\\\"']+)[\\\"'](?:\\uc744|\\ub97c)?\\s*(?:\\uc785\\ub825(?:\\ud558\\uace0)?|\\ud0c0\\uc774\\ud551(?:\\ud558\\uace0)?|type)",
        re.IGNORECASE,
    )
    _DOUBLE_CLICK_PATTERN = re.compile("(?:\\ub354\\ube14\\s*\\ud074\\ub9ad|double\\s*click)", re.IGNORECASE)
    _RIGHT_CLICK_PATTERN = re.compile("(?:\\uc624\\ub978\\ucabd\\s*\\ud074\\ub9ad|right\\s*click)", re.IGNORECASE)
    _CLICK_PATTERN = re.compile("(?:\\ud074\\ub9ad(?:\\ud55c|\\ud558\\uace0|\\ud574|\\ud558\\uae30)?|click)", re.IGNORECASE)
    _KEYS_PATTERN = re.compile(
        "(?P<keys>(?:(?:ctrl|alt|shift|win|meta)\\s*\\+\\s*)*(?:enter|tab|esc|escape|space|left|right|up|down|pgup|pgdn|f\\d+|[a-z0-9]))(?:\\ub97c|\\uc744)?\\s*(?:\\ub20c(?:\\ub7ec|\\ub7ec\\ub77c|\\ub7ec\\uc918|\\ub7ec\\uc8fc\\uc2dc|\\ub7ec\\ub77c)?|press)",
        re.IGNORECASE,
    )
    _HOTKEY_PATTERN = re.compile(
        "(?:\\ud56b\\ud0a4|hotkey)\\s*(?:\\ub294|\\uc744|:)?\\s*(?P<hotkey>(?:(?:ctrl|alt|shift|win|meta)\\s*\\+\\s*)+(?:[a-z0-9]|f\\d+|enter|tab|space))",
        re.IGNORECASE,
    )
    _BROWSER_TITLES = ("chrome", "edge", "chromium", "browser", "\ube0c\ub77c\uc6b0\uc800")

    def convert(
        self,
        text: str,
        *,
        existing_snippets: set[str] | None = None,
        existing_templates: set[str] | None = None,
        macro_name: str | None = None,
        hotkey: str | None = None,
        target_profile: str = "default",
    ) -> MacroAuthoringResult:
        normalized = self._normalize_source(text)
        if not normalized:
            raise ValueError("Natural language description is empty")

        state = _ConversionState(
            source_text=normalized,
            existing_snippets={item.lower() for item in (existing_snippets or set())},
            existing_templates={item.lower() for item in (existing_templates or set())},
        )
        actions = self._detect_actions(normalized)
        if not actions:
            raise ValueError("No supported macro actions were detected in the natural language description")

        macro = self._build_macro(
            actions,
            state,
            macro_name=macro_name,
            hotkey=hotkey or self._extract_hotkey(normalized),
            target_profile=target_profile,
        )
        validated = load_macro_from_data(macro)
        checklist = sorted(
            state.required_resources.values(),
            key=lambda item: (item.resource_type, item.resource_id.lower()),
        )
        return MacroAuthoringResult(
            source_text=normalized,
            macro_json=validated.model_dump(mode="json"),
            ambiguous_step_warnings=state.warnings,
            suggested_fallback_strategies=state.fallbacks,
            required_resources_checklist=checklist,
            target_adapter_recommendation=self._build_recommendation(state),
        )

    def _build_macro(
        self,
        actions: list[DetectedAction],
        state: _ConversionState,
        *,
        macro_name: str | None,
        hotkey: str | None,
        target_profile: str,
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        counters: dict[str, int] = {}
        last_ref: str | None = None
        focus_title: str | None = None

        for action in actions:
            kind = action.action_type
            if kind == "focus_window":
                counter = self._next_counter(counters, "focus_window")
                focus_title = action.payload["title_contains"]
                state.browser_context = state.browser_context or self._looks_like_browser_title(focus_title)
                state.desktop_window_context = state.desktop_window_context or not self._looks_like_browser_title(focus_title)
                self._add_score(
                    state,
                    "browser" if self._looks_like_browser_title(focus_title) else "uia",
                    3.0,
                    f"Window activation targets '{focus_title}'.",
                )
                steps.append(
                    {
                        "type": "focus_window",
                        "id": f"focus_window_{counter}",
                        "title_contains": focus_title,
                    }
                )
                if self._looks_like_browser_title(focus_title):
                    state.fallbacks.append(
                        SuggestedFallbackStrategy(
                            step_id=f"focus_window_{counter}",
                            message="If multiple Chromium windows match, refine the locator with an exact title, URL, or DOM anchor.",
                            rationale="`title_contains` is deterministic but broad enough to match several browser windows.",
                        )
                    )
                continue

            if kind == "open_page":
                counter = self._next_counter(counters, "open_page")
                state.browser_context = True
                self._add_score(state, "browser", 5.0, f"Explicit browser navigation to {action.payload['url']}.")
                steps.append(
                    {
                        "type": "open_page",
                        "id": f"open_page_{counter}",
                        "url": action.payload["url"],
                        "new_tab": True,
                        "wait_until": "load",
                    }
                )
                continue

            if kind == "find_text":
                counter = self._next_counter(counters, "find_text")
                step_id = f"find_text_{counter}"
                query = action.payload["query"]
                strategy = self._choose_text_strategy(action.payload.get("scope"), state)
                save_as = self._ref_name_for_query(query, counter)
                step = {
                    "type": "find_text",
                    "id": step_id,
                    "query": query,
                    "strategy": strategy,
                    "save_as": save_as,
                }
                if focus_title and strategy != "dom":
                    step["window"] = {"title_contains": focus_title}
                steps.append(step)
                last_ref = save_as
                self._register_text_diagnostics(step_id, query, strategy, action.payload.get("scope"), state)
                continue

            if kind == "find_image":
                counter = self._next_counter(counters, "find_image")
                step_id = f"find_image_{counter}"
                template_ref = action.payload["template"]
                field_name = "template_path" if self._looks_like_path(template_ref) else "template_id"
                save_as = self._ref_name_for_template(template_ref, counter)
                steps.append(
                    {
                        "type": "find_image",
                        "id": step_id,
                        field_name: template_ref,
                        "save_as": save_as,
                    }
                )
                last_ref = save_as
                self._track_resource(state, "template", template_ref)
                self._add_score(state, "image", 4.0, f"Image/template reference '{template_ref}' was requested.")
                state.fallbacks.append(
                    SuggestedFallbackStrategy(
                        step_id=step_id,
                        message="Constrain image matching with `region` or `search_region_hint` if duplicate icons exist.",
                        rationale="Image matching is more deterministic when the search area is anchored.",
                    )
                )
                continue

            if kind in {"click", "double_click", "right_click"}:
                last_ref = self._append_click_step(kind, counters, steps, last_ref, state)
                continue

            if kind == "type_text":
                counter = self._next_counter(counters, "type_text")
                step_id = f"type_text_{counter}"
                steps.append(
                    {
                        "type": "type_text",
                        "id": step_id,
                        "text": action.payload["text"],
                    }
                )
                state.warnings.append(
                    AmbiguityWarning(
                        step_id=step_id,
                        message="The destination field for typed text was not stated explicitly.",
                        assumption="The converter will type into whichever control is focused when the step runs.",
                    )
                )
                continue

            if kind == "paste_snippet":
                counter = self._next_counter(counters, "paste_snippet")
                step_id = f"paste_snippet_{counter}"
                snippet_id = action.payload["snippet_id"]
                steps.append(
                    {
                        "type": "paste_snippet",
                        "id": step_id,
                        "snippet_id": snippet_id,
                    }
                )
                self._track_resource(state, "snippet", snippet_id)
                state.warnings.append(
                    AmbiguityWarning(
                        step_id=step_id,
                        message="The snippet paste target was not stated explicitly.",
                        assumption="The converter assumes the intended field is already focused before the paste step runs.",
                    )
                )
                continue

            if kind == "press_keys":
                counter = self._next_counter(counters, "press_keys")
                step_id = f"press_keys_{counter}"
                steps.append(
                    {
                        "type": "press_keys",
                        "id": step_id,
                        "keys": action.payload["keys"],
                    }
                )
                state.warnings.append(
                    AmbiguityWarning(
                        step_id=step_id,
                        message=f"The key press '{action.payload['keys']}' does not name a target control.",
                        assumption="The converter assumes the currently focused application should receive the key press.",
                    )
                )
                continue

        if not steps:
            raise ValueError("Supported actions were detected, but none could be converted into deterministic macro steps")

        return {
            "schema_version": "2.0",
            "name": macro_name or self._derive_macro_name(actions, state),
            "description": state.source_text,
            "hotkey": hotkey,
            "target_profile": target_profile,
            "steps": steps,
        }

    def _append_click_step(
        self,
        kind: str,
        counters: dict[str, int],
        steps: list[dict[str, Any]],
        last_ref: str | None,
        state: _ConversionState,
    ) -> str | None:
        if last_ref is None:
            state.warnings.append(
                AmbiguityWarning(
                    message=f"A {kind.replace('_', ' ')} action was mentioned without a prior target reference.",
                    assumption="The converter skipped this action because there was no deterministic target.",
                )
            )
            return last_ref
        step_type = {
            "click": "click_ref",
            "double_click": "double_click_ref",
            "right_click": "right_click_ref",
        }[kind]
        counter = self._next_counter(counters, step_type)
        steps.append(
            {
                "type": step_type,
                "id": f"{step_type}_{counter}",
                "ref": last_ref,
            }
        )
        return last_ref

    def _detect_actions(self, source_text: str) -> list[DetectedAction]:
        actions: list[DetectedAction] = []
        consumed: list[tuple[int, int]] = []
        detectors = [
            self._detect_focus_window_actions,
            self._detect_open_page_actions,
            self._detect_find_text_actions,
            self._detect_find_image_actions,
            self._detect_paste_snippet_actions,
            self._detect_type_text_actions,
            self._detect_double_click_actions,
            self._detect_right_click_actions,
            self._detect_click_actions,
            self._detect_press_keys_actions,
        ]
        for detector in detectors:
            for action in detector(source_text):
                if self._is_overlapping(consumed, action.start, action.end):
                    continue
                actions.append(action)
                consumed.append((action.start, action.end))
        actions.sort(key=lambda item: (item.start, item.end))
        return actions

    def _detect_focus_window_actions(self, source_text: str) -> list[DetectedAction]:
        matches: list[DetectedAction] = []
        for pattern in self._FOCUS_WINDOW_PATTERNS:
            for match in pattern.finditer(source_text):
                title = match.group("title").strip()
                if not title:
                    continue
                matches.append(
                    DetectedAction(
                        action_type="focus_window",
                        start=match.start(),
                        end=match.end(),
                        payload={"title_contains": title},
                    )
                )
        return matches

    def _detect_open_page_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(
                action_type="open_page",
                start=match.start(),
                end=match.end(),
                payload={"url": match.group("url").strip()},
            )
            for match in self._OPEN_PAGE_PATTERN.finditer(source_text)
        ]

    def _detect_find_text_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(
                action_type="find_text",
                start=match.start(),
                end=match.end(),
                payload={
                    "scope": (match.group("scope") or "").strip(),
                    "query": match.group("query").strip(),
                },
            )
            for match in self._FIND_TEXT_PATTERN.finditer(source_text)
        ]

    def _detect_find_image_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(
                action_type="find_image",
                start=match.start(),
                end=match.end(),
                payload={"template": match.group("template").strip()},
            )
            for match in self._FIND_IMAGE_PATTERN.finditer(source_text)
        ]

    def _detect_paste_snippet_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(
                action_type="paste_snippet",
                start=match.start(),
                end=match.end(),
                payload={"snippet_id": match.group("snippet").strip()},
            )
            for match in self._PASTE_SNIPPET_PATTERN.finditer(source_text)
        ]

    def _detect_type_text_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(
                action_type="type_text",
                start=match.start(),
                end=match.end(),
                payload={"text": match.group("text").strip()},
            )
            for match in self._TYPE_TEXT_PATTERN.finditer(source_text)
        ]

    def _detect_double_click_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(action_type="double_click", start=match.start(), end=match.end())
            for match in self._DOUBLE_CLICK_PATTERN.finditer(source_text)
        ]

    def _detect_right_click_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(action_type="right_click", start=match.start(), end=match.end())
            for match in self._RIGHT_CLICK_PATTERN.finditer(source_text)
        ]

    def _detect_click_actions(self, source_text: str) -> list[DetectedAction]:
        return [
            DetectedAction(action_type="click", start=match.start(), end=match.end())
            for match in self._CLICK_PATTERN.finditer(source_text)
        ]

    def _detect_press_keys_actions(self, source_text: str) -> list[DetectedAction]:
        matches: list[DetectedAction] = []
        for match in self._KEYS_PATTERN.finditer(source_text):
            matches.append(
                DetectedAction(
                    action_type="press_keys",
                    start=match.start(),
                    end=match.end(),
                    payload={"keys": self._normalize_keys(match.group("keys"))},
                )
            )
        return matches

    def _extract_hotkey(self, source_text: str) -> str | None:
        match = self._HOTKEY_PATTERN.search(source_text)
        if not match:
            return None
        return self._normalize_keys(match.group("hotkey"))

    def _choose_text_strategy(self, scope: str | None, state: _ConversionState) -> str:
        normalized_scope = (scope or "").strip().lower()
        if normalized_scope.startswith("\ube0c\ub77c\uc6b0\uc800") or normalized_scope.startswith("browser") or normalized_scope.startswith("\ud398\uc774\uc9c0") or normalized_scope.startswith("page"):
            self._add_score(state, "browser", 4.0, "Text lookup is explicitly scoped to a browser page.")
            return "dom"
        if normalized_scope.startswith("\ud654\uba74") or normalized_scope.startswith("screen"):
            if state.browser_context:
                self._add_score(state, "browser", 3.0, "Text is on screen while the flow is browser-focused.")
                self._add_score(state, "ocr", 2.0, "Screen phrasing implies OCR may be needed.")
                self._add_score(state, "uia", 1.0, "UI Automation may help if the browser exposes accessibility text.")
                return "dom_or_uia_or_ocr"
            self._add_score(state, "ocr", 4.0, "Text lookup is explicitly scoped to the screen.")
            return "ocr"
        if normalized_scope.startswith("\ucc3d") or normalized_scope.startswith("window"):
            self._add_score(state, "uia", 3.0, "Text lookup is scoped to a window.")
            self._add_score(state, "ocr", 1.0, "Window text may still require OCR if accessibility is weak.")
            return "uia_or_ocr"
        if state.browser_context:
            self._add_score(state, "browser", 3.0, "The flow is browser-focused but the text lookup is not pinned to a single adapter.")
            self._add_score(state, "uia", 1.0, "Browser accessibility could be used as a fallback.")
            self._add_score(state, "ocr", 1.0, "OCR remains useful for inaccessible browser surfaces.")
            return "dom_or_uia_or_ocr"
        self._add_score(state, "uia", 2.0, "Generic desktop text lookup usually starts with UI Automation.")
        self._add_score(state, "ocr", 2.0, "OCR is a common fallback for generic desktop text lookup.")
        return "uia_or_ocr"

    def _register_text_diagnostics(
        self,
        step_id: str,
        query: str,
        strategy: str,
        scope: str | None,
        state: _ConversionState,
    ) -> None:
        normalized_scope = (scope or "").strip() or "implicit target"
        if strategy in {"dom_or_uia_or_ocr", "uia_or_ocr"}:
            state.warnings.append(
                AmbiguityWarning(
                    step_id=step_id,
                    message=f"Text search for '{query}' is ambiguous across multiple adapters.",
                    assumption=f"The converter chose `{strategy}` because the wording '{normalized_scope}' does not deterministically identify a single adapter.",
                )
            )
        if strategy == "dom_or_uia_or_ocr":
            state.fallbacks.append(
                SuggestedFallbackStrategy(
                    step_id=step_id,
                    message="If browser DOM access is unreliable, add an OCR anchor or an image fallback for the same target.",
                    rationale="Chromium surfaces can expose text through DOM, accessibility trees, or pixels depending on the page implementation.",
                    suggested_patch={"fallback_template_id": "capture_a_template_if_needed"},
                )
            )
        elif strategy == "ocr":
            state.fallbacks.append(
                SuggestedFallbackStrategy(
                    step_id=step_id,
                    message="Constrain OCR with a `region` or `anchor_text` if the same text appears multiple times.",
                    rationale="Region- or anchor-scoped OCR is more deterministic than full-screen OCR.",
                )
            )

    def _track_resource(self, state: _ConversionState, resource_type: str, resource_id: str) -> None:
        key = (resource_type, resource_id.lower())
        if key in state.required_resources:
            return
        exists = resource_id.lower() in (
            state.existing_snippets if resource_type == "snippet" else state.existing_templates
        )
        note = "" if exists else f"Create `{resource_id}` before executing the generated macro."
        state.required_resources[key] = RequiredResourceChecklistItem(
            resource_type=resource_type,
            resource_id=resource_id,
            exists=exists,
            note=note,
        )
        if not exists:
            state.warnings.append(
                AmbiguityWarning(
                    message=f"Referenced {resource_type} '{resource_id}' does not exist in the current workspace.",
                    assumption="The converter kept the reference in the macro JSON, but execution will fail until the resource is created.",
                )
            )

    def _build_recommendation(self, state: _ConversionState) -> AdapterRecommendation:
        if not state.adapter_scores:
            return AdapterRecommendation(
                adapter="uia",
                rationale="No strong browser, OCR, or image cues were detected, so Windows UI Automation is the safest default recommendation.",
                confidence=0.5,
            )
        adapter = sorted(
            state.adapter_scores.items(),
            key=lambda item: (-item[1], KEYWORD_PRIORITY[item[0]]),
        )[0][0]
        total = sum(state.adapter_scores.values()) or 1.0
        confidence = round(state.adapter_scores[adapter] / total, 2)
        rationale = state.adapter_reasons.get(adapter, [f"The prompt most strongly matched the `{adapter}` adapter."])[0]
        return AdapterRecommendation(adapter=adapter, rationale=rationale, confidence=confidence)

    def _derive_macro_name(self, actions: list[DetectedAction], state: _ConversionState) -> str:
        tokens: list[str] = []
        for action in actions:
            if action.action_type == "focus_window":
                token = self._slug_token(action.payload.get("title_contains", ""))
                if token:
                    tokens.append(token)
            elif action.action_type == "find_text":
                tokens.append(self._slug_token(action.payload.get("query", "")) or "text")
            elif action.action_type == "find_image":
                tokens.append(self._slug_token(action.payload.get("template", "")) or "image")
            elif action.action_type == "paste_snippet":
                tokens.append(self._slug_token(action.payload.get("snippet_id", "")) or "snippet")
        filtered = [token for token in tokens if token][:4]
        if not filtered:
            filtered = [self._build_recommendation(state).adapter, "macro"]
        return re.sub(r"_+", "_", "_".join(filtered)).strip("_") or "generated_macro"

    def _ref_name_for_query(self, query: str, counter: int) -> str:
        token = self._slug_token(query)
        return f"text_{token or counter}"

    def _ref_name_for_template(self, template_ref: str, counter: int) -> str:
        token = self._slug_token(template_ref)
        return f"image_{token or counter}"

    def _slug_token(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-zA-Z0-9]+", "_", normalized.lower()).strip("_")[:32]

    def _normalize_source(self, text: str) -> str:
        normalized = (
            text.replace("\r\n", "\n")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\s*\n\s*", " ", normalized)
        return normalized.strip()

    def _normalize_keys(self, keys: str) -> str:
        return re.sub(r"\s+", "", keys).lower()

    def _looks_like_browser_title(self, title: str | None) -> bool:
        normalized = (title or "").lower()
        return any(keyword in normalized for keyword in self._BROWSER_TITLES)

    def _looks_like_path(self, value: str) -> bool:
        normalized = value.lower()
        return any(normalized.endswith(suffix) for suffix in (".png", ".jpg", ".jpeg", ".bmp"))

    def _add_score(self, state: _ConversionState, adapter: str, value: float, reason: str) -> None:
        state.adapter_scores[adapter] = state.adapter_scores.get(adapter, 0.0) + value
        state.adapter_reasons.setdefault(adapter, [])
        if reason not in state.adapter_reasons[adapter]:
            state.adapter_reasons[adapter].append(reason)

    def _next_counter(self, counters: dict[str, int], key: str) -> int:
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    def _is_overlapping(self, spans: list[tuple[int, int]], start: int, end: int) -> bool:
        for left, right in spans:
            if start < right and end > left:
                return True
        return False
