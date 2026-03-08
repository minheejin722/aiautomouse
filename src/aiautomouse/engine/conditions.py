from __future__ import annotations

from aiautomouse.engine.models import (
    AllCondition,
    AnyCondition,
    ConditionSpec,
    ImageExistsCondition,
    LegacyConditionSpec,
    NotCondition,
    RefExistsCondition,
    StepSucceededCondition,
    TextExistsCondition,
    VariableEqualsCondition,
    WindowActiveCondition,
)
from aiautomouse.engine.results import ConditionEvaluationError
from aiautomouse.engine.targeting import build_image_target, build_text_target


class ConditionEvaluator:
    def evaluate(self, condition: ConditionSpec, ctx: object) -> bool:
        if condition.type == "always":
            return True
        if isinstance(condition, TextExistsCondition):
            target = build_text_target(
                query=ctx.render_string(condition.query),
                strategy=condition.strategy,
                window=condition.window,
                region=condition.region,
                anchor=condition.anchor,
                case_sensitive=condition.case_sensitive,
                match_mode=condition.match_mode,
                collapse_whitespace=condition.collapse_whitespace,
                fuzzy_threshold=condition.fuzzy_threshold,
                anchor_text=ctx.render_string(condition.anchor_text) if condition.anchor_text else None,
                anchor_match_mode=condition.anchor_match_mode,
                anchor_relative=condition.anchor_relative,
                anchor_max_distance=condition.anchor_max_distance,
                selection_policy=condition.selection_policy,
                monitor_index=condition.monitor_index,
                last_known_padding=condition.last_known_padding,
                fallback_template_id=condition.fallback_template_id,
                fallback_template_path=condition.fallback_template_path,
                fallback_confidence=condition.fallback_confidence,
            )
            try:
                ctx.resolver.resolve(ctx.resolve_target(target), ctx)
                return True
            except Exception:
                return False
        if isinstance(condition, ImageExistsCondition):
            target = build_image_target(
                template_id=condition.template_id,
                template_path=condition.template_path,
                region=condition.region,
                confidence=condition.confidence,
                search_region_hint=condition.search_region_hint,
                monitor_index=condition.monitor_index,
                use_grayscale=condition.use_grayscale,
                use_mask=condition.use_mask,
                multi_scale=condition.multi_scale,
                scales=condition.scales,
                top_n=condition.top_n,
                preferred_theme=condition.preferred_theme,
                preferred_dpi=condition.preferred_dpi,
                last_known_padding=condition.last_known_padding,
            )
            try:
                ctx.resolver.resolve(ctx.resolve_target(target), ctx)
                return True
            except Exception:
                return False
        if isinstance(condition, RefExistsCondition):
            return condition.ref in ctx.references
        if isinstance(condition, WindowActiveCondition):
            info = ctx.refresh_active_window()
            title = str(info.get("title") or "")
            class_name = str(info.get("class_name") or "")
            if condition.title and title != ctx.render_string(condition.title):
                return False
            if condition.title_contains and ctx.render_string(condition.title_contains).lower() not in title.lower():
                return False
            if condition.class_name and class_name != ctx.render_string(condition.class_name):
                return False
            return True
        if isinstance(condition, VariableEqualsCondition):
            expected = ctx.render_value(condition.value)
            actual = ctx.current_variables().get(condition.name)
            return actual == expected
        if isinstance(condition, StepSucceededCondition):
            return bool(ctx.step_outcomes.get(condition.step_id))
        if isinstance(condition, NotCondition):
            return not self.evaluate(condition.condition, ctx)
        if isinstance(condition, AnyCondition):
            return any(self.evaluate(item, ctx) for item in condition.conditions)
        if isinstance(condition, AllCondition):
            return all(self.evaluate(item, ctx) for item in condition.conditions)
        raise ConditionEvaluationError(f"Unsupported condition type: {condition.type}")

    def evaluate_legacy(self, condition: LegacyConditionSpec, ctx: object) -> bool:
        kind = condition.kind.lower()
        if kind == "always":
            return True
        if kind == "never":
            return False
        if kind == "target_exists":
            if condition.target is None:
                raise ConditionEvaluationError("target_exists requires target")
            try:
                ctx.resolver.resolve(ctx.resolve_target(condition.target), ctx)
                return True
            except Exception:
                return False
        if kind == "window_title_contains":
            active_title = ctx.window_manager.get_active_window_title()
            expected = ctx.render_string(str(condition.value or ""))
            return expected.lower() in active_title.lower()
        if kind == "uia_value_contains":
            if condition.target is None:
                raise ConditionEvaluationError("uia_value_contains requires target")
            try:
                match = ctx.resolver.resolve(ctx.resolve_target(condition.target), ctx)
            except Exception:
                return False
            haystack = " ".join(
                str(value)
                for value in (
                    match.text,
                    match.metadata.get("value"),
                    match.metadata.get("name"),
                )
                if value
            )
            needle = ctx.render_string(str(condition.value or ""))
            return needle.lower() in haystack.lower()
        raise ConditionEvaluationError(f"Unsupported legacy condition kind: {condition.kind}")
