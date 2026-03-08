from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiautomouse.engine.actions import ActionExecutor
from aiautomouse.engine.conditions import ConditionEvaluator
from aiautomouse.engine.loader import load_macro, resolve_retry_policy
from aiautomouse.engine.models import (
    AbortStep,
    CallSubmacroStep,
    ClickStep,
    ClickRefStep,
    ClickXYStep,
    DoubleClickStep,
    DoubleClickRefStep,
    FindImageStep,
    FindTextStep,
    FocusWindowStep,
    IfStep,
    ImageExistsCondition,
    LegacyCompatStep,
    MacroSpec,
    OpenPageStep,
    PasteSnippetStep,
    PressKeysStep,
    RetryBlockStep,
    RightClickStep,
    StepSpec,
    TextExistsCondition,
    TypeTextStep,
    UploadFilesStep,
    VerifyAllStep,
    VerifyAnyStep,
    VerifyImageStep,
    VerifyTextStep,
    WaitForImageStep,
    WaitForTextStep,
)
from aiautomouse.engine.results import (
    ActionExecutionError,
    EmergencyStopError,
    MacroRunResult,
    StepResult,
    StepStatus,
)
from aiautomouse.engine.targeting import build_image_target, build_text_target
from aiautomouse.resources.snippets import SnippetStore
from aiautomouse.resources.templates import TemplateStore


@dataclass
class StepExecutionOutcome:
    success: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    child_results: list[StepResult] = field(default_factory=list)


class MacroRunner:
    def __init__(
        self,
        condition_evaluator: ConditionEvaluator | None = None,
        action_executor: ActionExecutor | None = None,
    ) -> None:
        self.condition_evaluator = condition_evaluator or ConditionEvaluator()
        self.action_executor = action_executor or ActionExecutor()

    def run(self, macro: MacroSpec, ctx: object) -> MacroRunResult:
        started_at = time.perf_counter()
        ctx.macro = macro
        ctx._variable_stack = [dict(macro.variables)]
        ctx.artifacts.write_json("macro_resolved.json", macro.model_dump(mode="json"))
        ctx.event_logger.emit(
            "macro_started",
            macro=macro.name,
            mode=ctx.mode.value,
            schema_version=macro.schema_version,
        )
        overall_status = StepStatus.SUCCESS
        error_message: str | None = None
        try:
            step_results, success, error_message = self._execute_steps(macro.steps, ctx, namespace=macro.name)
            if not success:
                overall_status = StepStatus.FAILED
        except EmergencyStopError as exc:
            overall_status = StepStatus.CANCELLED
            error_message = str(exc)
            step_results = []
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        failed_step_id = ctx.state.get("failed_step_id")
        with contextlib.suppress(Exception):
            ctx.refresh_active_window()
        ctx.event_logger.emit(
            "macro_finished",
            macro=macro.name,
            status=overall_status.value,
            duration_ms=duration_ms,
            error=error_message,
            failed_step_id=failed_step_id,
            active_window=ctx.active_window_info,
            replay_log=str(getattr(ctx.artifacts, "events_path", "")),
        )
        summary_payload = {
            "run_id": ctx.run_id,
            "macro_name": macro.name,
            "status": overall_status.value,
            "duration_ms": duration_ms,
            "error": error_message,
            "failed_step_id": failed_step_id,
            "active_window": ctx.active_window_info,
            "screenshots": list(getattr(ctx, "screenshots", [])),
            "step_timings": dict(getattr(ctx, "step_timings", {})),
            "ocr_debug_keys": sorted(getattr(ctx, "ocr_debug_results", {}).keys()),
            "image_debug_keys": sorted(getattr(ctx, "image_debug_results", {}).keys()),
            "replay_log": str(getattr(ctx.artifacts, "events_path", "")),
        }
        if hasattr(ctx.artifacts, "write_run_summary"):
            summary_path = ctx.artifacts.write_run_summary(summary_payload)
        else:
            summary_path = ctx.artifacts.write_json("summary.json", summary_payload)
        return MacroRunResult(
            macro_name=macro.name,
            status=overall_status,
            duration_ms=duration_ms,
            steps=step_results,
            run_id=ctx.run_id,
            error=error_message,
            failed_step_id=failed_step_id,
            summary_path=str(summary_path),
        )

    def _execute_steps(self, steps: list[StepSpec], ctx: object, namespace: str) -> tuple[list[StepResult], bool, str | None]:
        results: list[StepResult] = []
        for step in steps:
            step_path = f"{namespace}.{step.id or step.type}"
            step_results, success, error = self._execute_step(step, ctx, step_path)
            results.extend(step_results)
            if not success:
                return results, False, error
        return results, True, None

    def _execute_step(self, step: StepSpec, ctx: object, step_path: str) -> tuple[list[StepResult], bool, str | None]:
        if isinstance(step, LegacyCompatStep):
            return self._execute_legacy_step(step, ctx, step_path)

        started_at = ctx.mark_step_started(step_path)
        initial_artifacts = self._record_step_artifacts(ctx, step, step_path, "before", attempt=0)
        if step.when and not self.condition_evaluator.evaluate(step.when, ctx):
            duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.SKIPPED.value)
            final_artifacts = self._record_step_artifacts(ctx, step, step_path, "skipped", attempt=0, status=StepStatus.SKIPPED.value)
            ctx.event_logger.emit(
                "step_skipped",
                step_id=step.id,
                step_type=step.type,
                step_path=step_path,
                duration_ms=duration_ms,
                active_window=ctx.active_window_info,
                before_screenshot=initial_artifacts.get("before_screenshot"),
                after_screenshot=final_artifacts.get("skipped_screenshot"),
            )
            ctx.register_step_outcome(step.id or step_path, False)
            return (
                [
                    StepResult(
                        step_id=step.id or step_path,
                        step_type=step.type,
                        status=StepStatus.SKIPPED,
                        attempts=0,
                        duration_ms=duration_ms,
                        step_path=step_path,
                        action_details=self._merge_details({}, initial_artifacts, final_artifacts),
                    )
                ],
                True,
                None,
            )

        if isinstance(step, RetryBlockStep):
            return self._execute_retry_block(step, ctx, step_path, started_at)

        policy = resolve_retry_policy(step.retry, ctx.macro.retry_policies if ctx.macro else {})
        last_outcome = StepExecutionOutcome(success=False, error="step did not run")
        for attempt in range(1, policy.max_attempts + 1):
            ctx.check_cancelled()
            ctx.mark_retry_attempt(step_path, attempt)
            ctx.event_logger.emit(
                "step_started",
                step_id=step.id,
                step_type=step.type,
                step_path=step_path,
                attempt=attempt,
                active_window=ctx.active_window_info,
                before_screenshot=initial_artifacts.get("before_screenshot"),
            )
            last_outcome = self._execute_step_once(step, ctx, step_path)
            if last_outcome.success:
                duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.SUCCESS.value)
                final_artifacts = self._record_step_artifacts(
                    ctx,
                    step,
                    step_path,
                    "after",
                    attempt=attempt,
                    status=StepStatus.SUCCESS.value,
                    details=last_outcome.details,
                )
                result = StepResult(
                    step_id=step.id or step_path,
                    step_type=step.type,
                    status=StepStatus.SUCCESS,
                    attempts=attempt,
                    duration_ms=duration_ms,
                    step_path=step_path,
                    action_details=self._merge_details(last_outcome.details, initial_artifacts, final_artifacts),
                )
                ctx.register_step_outcome(step.id or step_path, True)
                ctx.event_logger.emit(
                    "step_succeeded",
                    step_id=step.id,
                    step_type=step.type,
                    step_path=step_path,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    active_window=ctx.active_window_info,
                    action_details=result.action_details,
                )
                return last_outcome.child_results + [result], True, None
            if attempt < policy.max_attempts:
                ctx.sleep(self._retry_delay(policy.delay_ms, policy.backoff_multiplier, attempt))

        ctx.state["failed_step_id"] = step.id or step_path
        screenshot_path = ctx.artifacts.capture_failure_screenshot(step.id or step.type, ctx.screen_capture)
        final_artifacts = self._record_step_artifacts(
            ctx,
            step,
            step_path,
            "failed",
            attempt=policy.max_attempts,
            status=StepStatus.FAILED.value,
            error=last_outcome.error,
            details=last_outcome.details,
        )
        if screenshot_path:
            last_outcome.details["failure_screenshot"] = str(screenshot_path)
            ctx.remember_screenshot(str(screenshot_path))
        duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.FAILED.value)
        result = StepResult(
            step_id=step.id or step_path,
            step_type=step.type,
            status=StepStatus.FAILED,
            attempts=policy.max_attempts,
            duration_ms=duration_ms,
            step_path=step_path,
            error=last_outcome.error,
            action_details=self._merge_details(last_outcome.details, initial_artifacts, final_artifacts),
        )
        ctx.register_step_outcome(step.id or step_path, False)
        ctx.event_logger.emit(
            "step_failed",
            step_id=step.id,
            step_type=step.type,
            step_path=step_path,
            attempts=policy.max_attempts,
            error=last_outcome.error,
            duration_ms=duration_ms,
            active_window=ctx.active_window_info,
            action_details=result.action_details,
        )
        return last_outcome.child_results + [result], False, last_outcome.error

    def _execute_step_once(self, step: StepSpec, ctx: object, step_path: str) -> StepExecutionOutcome:
        try:
            if isinstance(step, FocusWindowStep):
                return StepExecutionOutcome(success=True, details=self.action_executor.focus_window(
                    ctx,
                    title=ctx.render_string(step.title) if step.title else None,
                    title_contains=ctx.render_string(step.title_contains) if step.title_contains else None,
                    class_name=ctx.render_string(step.class_name) if step.class_name else None,
                    anchor=step.anchor,
                ))
            if isinstance(step, OpenPageStep):
                details = self.action_executor.open_page(
                    ctx,
                    url=ctx.render_string(step.url),
                    new_tab=step.new_tab,
                    new_window=step.new_window,
                    reuse_existing=step.reuse_existing,
                    title_contains=ctx.render_string(step.title_contains) if step.title_contains else None,
                    url_contains=ctx.render_string(step.url_contains) if step.url_contains else None,
                    wait_until=step.wait_until,
                )
                if step.save_as:
                    ctx.state.setdefault("browser_pages", {})
                    ctx.state["browser_pages"][step.save_as] = details
                return StepExecutionOutcome(success=True, details=details)
            if isinstance(step, WaitForTextStep):
                return self._wait_for_text(step, ctx)
            if isinstance(step, WaitForImageStep):
                return self._wait_for_image(step, ctx)
            if isinstance(step, FindTextStep):
                return self._resolve_find_text(step, ctx)
            if isinstance(step, FindImageStep):
                return self._resolve_find_image(step, ctx)
            if isinstance(step, ClickRefStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.click_ref(step.ref, ctx, offset=step.offset),
                )
            if isinstance(step, ClickStep):
                return self._execute_click_variant(step, ctx, button="left", double=False)
            if isinstance(step, ClickXYStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.click_xy(ctx.resolve_int(step.x), ctx.resolve_int(step.y), ctx),
                )
            if isinstance(step, DoubleClickRefStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.click_ref(step.ref, ctx, double=True, offset=step.offset),
                )
            if isinstance(step, DoubleClickStep):
                return self._execute_click_variant(step, ctx, button="left", double=True)
            if step.type == "right_click_ref":
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.click_ref(step.ref, ctx, button="right", offset=step.offset),
                )
            if isinstance(step, RightClickStep):
                return self._execute_click_variant(step, ctx, button="right", double=False)
            if isinstance(step, TypeTextStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.type_text(ctx.render_string(step.text), ctx, ref=step.ref),
                )
            if isinstance(step, PasteSnippetStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.paste_snippet(step.snippet_id, ctx, ref=step.ref),
                )
            if isinstance(step, PressKeysStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.press_keys(ctx.render_value(step.keys), ctx),
                )
            if isinstance(step, UploadFilesStep):
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.upload_files(
                        ctx.render_value(step.files),
                        ctx,
                        ref=step.ref,
                        target=step.target,
                        allow_file_chooser=step.allow_file_chooser,
                    ),
                )
            if isinstance(step, VerifyAnyStep):
                outcomes = [self.condition_evaluator.evaluate(condition, ctx) for condition in step.conditions]
                if any(outcomes):
                    return StepExecutionOutcome(success=True, details={"outcomes": outcomes})
                return StepExecutionOutcome(success=False, error="verify_any failed", details={"outcomes": outcomes})
            if isinstance(step, VerifyTextStep):
                condition = TextExistsCondition(
                    type="text_exists",
                    query=step.query,
                    strategy=step.strategy,
                    window=step.window,
                    region=step.region,
                    case_sensitive=step.case_sensitive,
                    anchor=step.anchor,
                    match_mode=step.match_mode,
                    collapse_whitespace=step.collapse_whitespace,
                    fuzzy_threshold=step.fuzzy_threshold,
                    anchor_text=step.anchor_text,
                    anchor_match_mode=step.anchor_match_mode,
                    anchor_relative=step.anchor_relative,
                    anchor_max_distance=step.anchor_max_distance,
                    selection_policy=step.selection_policy,
                    monitor_index=step.monitor_index,
                    last_known_padding=step.last_known_padding,
                    fallback_template_id=step.fallback_template_id,
                    fallback_template_path=step.fallback_template_path,
                    fallback_confidence=step.fallback_confidence,
                )
                outcome = self.condition_evaluator.evaluate(condition, ctx)
                if outcome:
                    return StepExecutionOutcome(success=True, details={"condition": condition.model_dump(mode="python")})
                return StepExecutionOutcome(success=False, error="verify_text failed")
            if isinstance(step, VerifyImageStep):
                condition = ImageExistsCondition(
                    type="image_exists",
                    template_id=step.template_id,
                    template_path=step.template_path,
                    region=step.region,
                    confidence=step.confidence,
                    search_region_hint=step.search_region_hint,
                    monitor_index=step.monitor_index,
                    use_grayscale=step.use_grayscale,
                    use_mask=step.use_mask,
                    multi_scale=step.multi_scale,
                    scales=step.scales,
                    top_n=step.top_n,
                    preferred_theme=step.preferred_theme,
                    preferred_dpi=step.preferred_dpi,
                    last_known_padding=step.last_known_padding,
                )
                outcome = self.condition_evaluator.evaluate(condition, ctx)
                if outcome:
                    return StepExecutionOutcome(success=True, details={"condition": condition.model_dump(mode="python")})
                return StepExecutionOutcome(success=False, error="verify_image failed")
            if isinstance(step, VerifyAllStep):
                outcomes = [self.condition_evaluator.evaluate(condition, ctx) for condition in step.conditions]
                if all(outcomes):
                    return StepExecutionOutcome(success=True, details={"outcomes": outcomes})
                return StepExecutionOutcome(success=False, error="verify_all failed", details={"outcomes": outcomes})
            if isinstance(step, IfStep):
                branch = "then" if self.condition_evaluator.evaluate(step.condition, ctx) else "else"
                branch_steps = step.then_steps if branch == "then" else step.else_steps
                child_results, success, error = self._execute_steps(branch_steps, ctx, namespace=f"{step_path}.{branch}")
                return StepExecutionOutcome(
                    success=success,
                    error=error,
                    details={"branch": branch},
                    child_results=child_results,
                )
            if isinstance(step, CallSubmacroStep):
                return self._execute_call_submacro(step, ctx, step_path)
            if isinstance(step, AbortStep):
                return StepExecutionOutcome(success=False, error=ctx.render_string(step.message))
        except EmergencyStopError:
            raise
        except Exception as exc:
            return StepExecutionOutcome(success=False, error=str(exc))
        return StepExecutionOutcome(success=False, error=f"Unsupported step type: {step.type}")

    def _execute_click_variant(self, step, ctx: object, *, button: str, double: bool) -> StepExecutionOutcome:
        if getattr(step, "ref", None):
            return StepExecutionOutcome(
                success=True,
                details=self.action_executor.click_ref(step.ref, ctx, button=button, double=double, offset=step.offset),
            )
        if getattr(step, "target", None) is not None:
            save_as = step.save_as or (f"{step.id}_target" if step.id else f"{step.type}_target")
            match = self.action_executor.resolve_target(step.target, ctx, save_as=save_as, label=step.type)
            if button == "right":
                return StepExecutionOutcome(
                    success=True,
                    details=self.action_executor.click_ref(save_as, ctx, button="right", offset=step.offset),
                )
            return StepExecutionOutcome(
                success=True,
                details=self.action_executor.click_ref(save_as, ctx, double=double, offset=step.offset),
            )
        x = ctx.resolve_int(step.x)
        y = ctx.resolve_int(step.y)
        if button == "right":
            return StepExecutionOutcome(success=True, details=self.action_executor.right_click_xy(x, y, ctx))
        if double:
            return StepExecutionOutcome(success=True, details=self.action_executor.double_click_xy(x, y, ctx))
        return StepExecutionOutcome(success=True, details=self.action_executor.click_xy(x, y, ctx))

    def _resolve_find_text(self, step: FindTextStep, ctx: object) -> StepExecutionOutcome:
        target = build_text_target(
            query=ctx.render_string(step.query),
            strategy=step.strategy,
            window=step.window,
            region=step.region,
            anchor=step.anchor,
            case_sensitive=step.case_sensitive,
            confidence=step.confidence,
            match_mode=step.match_mode,
            collapse_whitespace=step.collapse_whitespace,
            fuzzy_threshold=step.fuzzy_threshold,
            anchor_text=ctx.render_string(step.anchor_text) if step.anchor_text else None,
            anchor_match_mode=step.anchor_match_mode,
            anchor_relative=step.anchor_relative,
            anchor_max_distance=step.anchor_max_distance,
            selection_policy=step.selection_policy,
            monitor_index=step.monitor_index,
            last_known_padding=step.last_known_padding,
            fallback_template_id=step.fallback_template_id,
            fallback_template_path=step.fallback_template_path,
            fallback_confidence=step.fallback_confidence,
        )
        match = self.action_executor.resolve_target(target, ctx, save_as=step.save_as, label=step.type)
        return StepExecutionOutcome(
            success=True,
            details={"match": match.to_dict(), "save_as": step.save_as},
        )

    def _resolve_find_image(self, step: FindImageStep, ctx: object) -> StepExecutionOutcome:
        target = build_image_target(
            template_id=step.template_id,
            template_path=step.template_path,
            region=step.region,
            confidence=step.confidence,
            search_region_hint=step.search_region_hint,
            monitor_index=step.monitor_index,
            use_grayscale=step.use_grayscale,
            use_mask=step.use_mask,
            multi_scale=step.multi_scale,
            scales=step.scales,
            top_n=step.top_n,
            preferred_theme=step.preferred_theme,
            preferred_dpi=step.preferred_dpi,
            last_known_padding=step.last_known_padding,
        )
        match = self.action_executor.resolve_target(target, ctx, save_as=step.save_as, label=step.type)
        return StepExecutionOutcome(
            success=True,
            details={"match": match.to_dict(), "save_as": step.save_as},
        )

    def _wait_for_text(self, step: WaitForTextStep, ctx: object) -> StepExecutionOutcome:
        condition = TextExistsCondition(
            type="text_exists",
            query=step.query,
            strategy=step.strategy,
            window=step.window,
            region=step.region,
            case_sensitive=step.case_sensitive,
            anchor=step.anchor,
            match_mode=step.match_mode,
            collapse_whitespace=step.collapse_whitespace,
            fuzzy_threshold=step.fuzzy_threshold,
            anchor_text=step.anchor_text,
            anchor_match_mode=step.anchor_match_mode,
            anchor_relative=step.anchor_relative,
            anchor_max_distance=step.anchor_max_distance,
            selection_policy=step.selection_policy,
            monitor_index=step.monitor_index,
            last_known_padding=step.last_known_padding,
            fallback_template_id=step.fallback_template_id,
            fallback_template_path=step.fallback_template_path,
            fallback_confidence=step.fallback_confidence,
        )
        if not self._wait_for_condition(condition, step.timeout_ms or 5000, ctx):
            return StepExecutionOutcome(success=False, error=f"Timed out waiting for text '{step.query}'")
        return self._resolve_find_text(
            FindTextStep(
                type="find_text",
                id=step.id,
                name=step.name,
                query=step.query,
                strategy=step.strategy,
                window=step.window,
                region=step.region,
                case_sensitive=step.case_sensitive,
                anchor=step.anchor,
                confidence=step.confidence,
                save_as=step.save_as,
                match_mode=step.match_mode,
                collapse_whitespace=step.collapse_whitespace,
                fuzzy_threshold=step.fuzzy_threshold,
                anchor_text=step.anchor_text,
                anchor_match_mode=step.anchor_match_mode,
                anchor_relative=step.anchor_relative,
                anchor_max_distance=step.anchor_max_distance,
                selection_policy=step.selection_policy,
                monitor_index=step.monitor_index,
                last_known_padding=step.last_known_padding,
                fallback_template_id=step.fallback_template_id,
                fallback_template_path=step.fallback_template_path,
                fallback_confidence=step.fallback_confidence,
            ),
            ctx,
        )

    def _wait_for_image(self, step: WaitForImageStep, ctx: object) -> StepExecutionOutcome:
        condition = ImageExistsCondition(
            type="image_exists",
            template_id=step.template_id,
            template_path=step.template_path,
            region=step.region,
            confidence=step.confidence,
            search_region_hint=step.search_region_hint,
            monitor_index=step.monitor_index,
            use_grayscale=step.use_grayscale,
            use_mask=step.use_mask,
            multi_scale=step.multi_scale,
            scales=step.scales,
            top_n=step.top_n,
            preferred_theme=step.preferred_theme,
            preferred_dpi=step.preferred_dpi,
            last_known_padding=step.last_known_padding,
        )
        if not self._wait_for_condition(condition, step.timeout_ms or 5000, ctx):
            return StepExecutionOutcome(success=False, error="Timed out waiting for image")
        return self._resolve_find_image(
            FindImageStep(
                type="find_image",
                id=step.id,
                name=step.name,
                template_id=step.template_id,
                template_path=step.template_path,
                region=step.region,
                confidence=step.confidence,
                save_as=step.save_as,
                search_region_hint=step.search_region_hint,
                monitor_index=step.monitor_index,
                use_grayscale=step.use_grayscale,
                use_mask=step.use_mask,
                multi_scale=step.multi_scale,
                scales=step.scales,
                top_n=step.top_n,
                preferred_theme=step.preferred_theme,
                preferred_dpi=step.preferred_dpi,
                last_known_padding=step.last_known_padding,
            ),
            ctx,
        )

    def _execute_retry_block(
        self,
        step: RetryBlockStep,
        ctx: object,
        step_path: str,
        started_at: float,
    ) -> tuple[list[StepResult], bool, str | None]:
        policy = resolve_retry_policy(step.policy or step.retry, ctx.macro.retry_policies if ctx.macro else {})
        last_results: list[StepResult] = []
        last_error: str | None = None
        initial_artifacts = self._record_step_artifacts(ctx, step, step_path, "before", attempt=0)
        for attempt in range(1, policy.max_attempts + 1):
            ctx.check_cancelled()
            ctx.mark_retry_attempt(step_path, attempt)
            ctx.event_logger.emit(
                "step_started",
                step_id=step.id,
                step_type=step.type,
                step_path=step_path,
                attempt=attempt,
                active_window=ctx.active_window_info,
                before_screenshot=initial_artifacts.get("before_screenshot"),
            )
            child_results, success, error = self._execute_steps(step.steps, ctx, namespace=f"{step_path}.attempt_{attempt}")
            last_results = child_results
            last_error = error
            if success:
                duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.SUCCESS.value)
                final_artifacts = self._record_step_artifacts(
                    ctx,
                    step,
                    step_path,
                    "after",
                    attempt=attempt,
                    status=StepStatus.SUCCESS.value,
                )
                result = StepResult(
                    step_id=step.id or step_path,
                    step_type=step.type,
                    status=StepStatus.SUCCESS,
                    attempts=attempt,
                    duration_ms=duration_ms,
                    step_path=step_path,
                    action_details=self._merge_details({"policy": policy.model_dump(mode="python")}, initial_artifacts, final_artifacts),
                )
                ctx.register_step_outcome(step.id or step_path, True)
                ctx.event_logger.emit(
                    "step_succeeded",
                    step_id=step.id,
                    step_type=step.type,
                    step_path=step_path,
                    attempt=attempt,
                    duration_ms=duration_ms,
                    active_window=ctx.active_window_info,
                    action_details=result.action_details,
                )
                return last_results + [result], True, None
            if attempt < policy.max_attempts:
                ctx.sleep(self._retry_delay(policy.delay_ms, policy.backoff_multiplier, attempt))

        ctx.state["failed_step_id"] = step.id or step_path
        screenshot_path = ctx.artifacts.capture_failure_screenshot(step.id or step.type, ctx.screen_capture)
        details = {"policy": policy.model_dump(mode="python")}
        if screenshot_path:
            details["failure_screenshot"] = str(screenshot_path)
            ctx.remember_screenshot(str(screenshot_path))
        details = self._merge_details(
            details,
            initial_artifacts,
            self._record_step_artifacts(
                ctx,
                step,
                step_path,
                "failed",
                attempt=policy.max_attempts,
                status=StepStatus.FAILED.value,
                error=last_error,
            ),
        )
        duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.FAILED.value)
        result = StepResult(
            step_id=step.id or step_path,
            step_type=step.type,
            status=StepStatus.FAILED,
            attempts=policy.max_attempts,
            duration_ms=duration_ms,
            step_path=step_path,
            error=last_error,
            action_details=details,
        )
        ctx.register_step_outcome(step.id or step_path, False)
        ctx.event_logger.emit(
            "step_failed",
            step_id=step.id,
            step_type=step.type,
            step_path=step_path,
            attempts=policy.max_attempts,
            error=last_error,
            duration_ms=duration_ms,
            active_window=ctx.active_window_info,
            action_details=result.action_details,
        )
        return last_results + [result], False, last_error

    def _execute_call_submacro(self, step: CallSubmacroStep, ctx: object, step_path: str) -> StepExecutionOutcome:
        if step.submacro:
            if step.submacro not in ctx.macro.submacros:
                return StepExecutionOutcome(success=False, error=f"Unknown submacro: {step.submacro}")
            submacro = ctx.macro.submacros[step.submacro]
            with ctx.push_variables({**submacro.variables, **step.with_variables}):
                child_results, success, error = self._execute_steps(
                    submacro.steps,
                    ctx,
                    namespace=f"{step_path}.submacro.{step.submacro}",
                )
            return StepExecutionOutcome(
                success=success,
                error=error,
                details={"submacro": step.submacro},
                child_results=child_results,
            )
        external_path = (Path(ctx.macro_path).parent / step.path).resolve()
        external_macro = load_macro(external_path)
        external_snippets = SnippetStore.from_macro(external_macro, external_path)
        external_templates = TemplateStore.from_macro(external_macro, external_path)
        with self._macro_scope(ctx, external_macro, external_path, external_snippets, external_templates):
            with ctx.push_variables(step.with_variables):
                child_results, success, error = self._execute_steps(
                    external_macro.steps,
                    ctx,
                    namespace=f"{step_path}.macro.{external_macro.name}",
                )
        return StepExecutionOutcome(
            success=success,
            error=error,
            details={"path": str(external_path)},
            child_results=child_results,
        )

    def _execute_legacy_step(self, step: LegacyCompatStep, ctx: object, step_path: str) -> tuple[list[StepResult], bool, str | None]:
        started_at = ctx.mark_step_started(step_path)
        initial_artifacts = self._record_step_artifacts(ctx, step, step_path, "before", attempt=0)
        legacy = step.legacy
        last_error: str | None = None
        last_details: dict[str, Any] = {}
        attempts = max(1, legacy.retry.attempts)
        for attempt in range(1, attempts + 1):
            ctx.check_cancelled()
            ctx.mark_retry_attempt(step_path, attempt)
            ctx.event_logger.emit(
                "step_started",
                step_id=step.id,
                step_type="legacy_compat",
                step_path=step_path,
                attempt=attempt,
                active_window=ctx.active_window_info,
                before_screenshot=initial_artifacts.get("before_screenshot"),
            )
            action_ran = False
            try:
                if not self._wait_for_legacy_condition(legacy.precondition, legacy.timeout_ms, ctx):
                    last_error = f"Precondition timeout for step '{legacy.id}'"
                else:
                    last_details = self.action_executor.execute_legacy(legacy.action, ctx)
                    action_ran = True
                    if self._wait_for_legacy_condition(legacy.postcondition, legacy.timeout_ms, ctx):
                        duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.SUCCESS.value)
                        final_artifacts = self._record_step_artifacts(
                            ctx,
                            step,
                            step_path,
                            "after",
                            attempt=attempt,
                            status=StepStatus.SUCCESS.value,
                            details=last_details,
                        )
                        result = StepResult(
                            step_id=step.id or step_path,
                            step_type="legacy_compat",
                            status=StepStatus.SUCCESS,
                            attempts=attempt,
                            duration_ms=duration_ms,
                            step_path=step_path,
                            action_details=self._merge_details(last_details, initial_artifacts, final_artifacts),
                        )
                        ctx.register_step_outcome(step.id or step_path, True)
                        ctx.event_logger.emit(
                            "step_succeeded",
                            step_id=step.id,
                            step_type="legacy_compat",
                            step_path=step_path,
                            attempt=attempt,
                            duration_ms=duration_ms,
                            active_window=ctx.active_window_info,
                            action_details=result.action_details,
                        )
                        return [result], True, None
                    last_error = f"Postcondition timeout for step '{legacy.id}'"
            except Exception as exc:
                last_error = str(exc)

            if action_ran:
                try:
                    self.action_executor.execute_legacy(legacy.rollback, ctx)
                except Exception:
                    pass
            if attempt < attempts:
                ctx.sleep(legacy.retry.delay_ms)

        try:
            last_details["fallback"] = self.action_executor.execute_legacy(legacy.fallback, ctx)
        except Exception:
            pass
        ctx.state["failed_step_id"] = step.id or step_path
        screenshot_path = ctx.artifacts.capture_failure_screenshot(step.id or step.type, ctx.screen_capture)
        if screenshot_path:
            last_details["failure_screenshot"] = str(screenshot_path)
            ctx.remember_screenshot(str(screenshot_path))
        final_artifacts = self._record_step_artifacts(
            ctx,
            step,
            step_path,
            "failed",
            attempt=attempts,
            status=StepStatus.FAILED.value,
            error=last_error,
            details=last_details,
        )
        duration_ms = ctx.mark_step_finished(step_path, started_at, StepStatus.FAILED.value)
        result = StepResult(
            step_id=step.id or step_path,
            step_type="legacy_compat",
            status=StepStatus.FAILED,
            attempts=attempts,
            duration_ms=duration_ms,
            step_path=step_path,
            error=last_error,
            action_details=self._merge_details(last_details, initial_artifacts, final_artifacts),
        )
        ctx.register_step_outcome(step.id or step_path, False)
        ctx.event_logger.emit(
            "step_failed",
            step_id=step.id,
            step_type="legacy_compat",
            step_path=step_path,
            attempts=attempts,
            error=last_error,
            duration_ms=duration_ms,
            active_window=ctx.active_window_info,
            action_details=result.action_details,
        )
        return [result], False, last_error

    def _wait_for_condition(self, condition, timeout_ms: int, ctx: object) -> bool:
        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        while time.perf_counter() <= deadline:
            ctx.check_cancelled()
            if self.condition_evaluator.evaluate(condition, ctx):
                return True
            ctx.sleep(ctx.settings.poll_interval_ms)
        return False

    def _wait_for_legacy_condition(self, condition, timeout_ms: int, ctx: object) -> bool:
        deadline = time.perf_counter() + (timeout_ms / 1000.0)
        while time.perf_counter() <= deadline:
            ctx.check_cancelled()
            if self.condition_evaluator.evaluate_legacy(condition, ctx):
                return True
            ctx.sleep(ctx.settings.poll_interval_ms)
        return False

    def _retry_delay(self, delay_ms: int, backoff_multiplier: float, attempt: int) -> int:
        return int(delay_ms * (backoff_multiplier ** max(0, attempt - 1)))

    def _record_step_artifacts(
        self,
        ctx: object,
        step: StepSpec,
        step_path: str,
        phase: str,
        *,
        attempt: int,
        status: str | None = None,
        error: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_id": step.id or step_path,
            "step_type": step.type,
            "step_path": step_path,
            "phase": phase,
            "attempt": attempt,
            "status": status,
            "error": error,
            "details": details or {},
            "retry_counter": getattr(ctx, "retry_counters", {}).get(step_path, attempt),
            "ocr_debug_keys": sorted(getattr(ctx, "ocr_debug_results", {}).keys()),
            "image_debug_keys": sorted(getattr(ctx, "image_debug_results", {}).keys()),
            "references": sorted(getattr(ctx, "references", {}).keys()),
        }
        screenshot_path = None
        diagnostics = getattr(ctx.settings, "diagnostics", None)
        if diagnostics is None or diagnostics.capture_active_window_snapshot:
            with contextlib.suppress(Exception):
                payload["active_window"] = ctx.refresh_active_window()
        if (
            diagnostics is None or diagnostics.capture_before_after_screenshots
        ) and hasattr(ctx.artifacts, "capture_step_screenshot"):
            screenshot = ctx.artifacts.capture_step_screenshot(step_path, phase, ctx.screen_capture)
            if screenshot:
                screenshot_path = str(screenshot)
                ctx.remember_screenshot(screenshot_path)
        payload["screenshot"] = screenshot_path
        snapshot_path = None
        if hasattr(ctx.artifacts, "write_step_snapshot"):
            with contextlib.suppress(Exception):
                snapshot_path = ctx.artifacts.write_step_snapshot(step_path, phase, payload)
        return {
            f"{phase}_step_snapshot_phase": phase,
            f"{phase}_screenshot": screenshot_path,
            f"{phase}_active_window_snapshot": payload.get("active_window"),
            f"{phase}_step_snapshot_path": str(snapshot_path) if snapshot_path else None,
        }

    def _merge_details(self, base: dict[str, Any] | None, *extras: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base or {})
        for payload in extras:
            merged.update({key: value for key, value in payload.items() if value is not None})
        return merged

    @contextlib.contextmanager
    def _macro_scope(self, ctx: object, macro: MacroSpec, macro_path: Path, snippets, templates):
        previous_macro = ctx.macro
        previous_macro_path = ctx.macro_path
        previous_snippets = ctx.snippets
        previous_templates = ctx.templates
        try:
            ctx.macro = macro
            ctx.macro_path = macro_path
            ctx.snippets = snippets
            ctx.templates = templates
            yield
        finally:
            ctx.macro = previous_macro
            ctx.macro_path = previous_macro_path
            ctx.snippets = previous_snippets
            ctx.templates = previous_templates
