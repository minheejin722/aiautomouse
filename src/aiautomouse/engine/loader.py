from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from aiautomouse.engine.models import (
    CURRENT_SCHEMA_VERSION,
    LEGACY_SCHEMA_VERSION,
    LegacyMacroSpec,
    MacroSpec,
    RetryPolicySpec,
)


def load_macro(path: str | Path) -> MacroSpec:
    macro_path = Path(path)
    raw = macro_path.read_text(encoding="utf-8-sig")
    data = _load_structured_data(macro_path, raw)
    return load_macro_from_data(data)


def load_macro_from_data(data: dict[str, Any]) -> MacroSpec:
    normalized = copy.deepcopy(data)
    if _is_legacy_macro(normalized):
        normalized = migrate_legacy_macro(normalized)
    normalized.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    normalized = assign_step_ids(normalized)
    spec = MacroSpec.model_validate(normalized)
    return apply_defaults(spec)


def apply_defaults(spec: MacroSpec) -> MacroSpec:
    defaults = spec.defaults or {}
    if not defaults:
        return spec
    payload = spec.model_dump(mode="python")
    payload["steps"] = _apply_defaults_to_steps(payload["steps"], defaults)
    for name, submacro in payload.get("submacros", {}).items():
        submacro["steps"] = _apply_defaults_to_steps(submacro.get("steps", []), defaults, prefix=name)
    return MacroSpec.model_validate(payload)


def macro_to_dict(spec: MacroSpec) -> dict[str, Any]:
    return spec.model_dump(mode="json")


def migrate_legacy_macro(data: dict[str, Any]) -> dict[str, Any]:
    legacy = LegacyMacroSpec.model_validate(data)
    migrated_steps: list[dict[str, Any]] = []
    for step in legacy.steps:
        migrated_steps.append(
            {
                "type": "legacy_compat",
                "id": step.id,
                "name": step.name,
                "timeout_ms": step.timeout_ms,
                "retry": {
                    "max_attempts": step.retry.attempts,
                    "delay_ms": step.retry.delay_ms,
                },
                "legacy": step.model_dump(mode="python"),
            }
        )
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "name": legacy.name,
        "description": legacy.description,
        "defaults": legacy.defaults,
        "resources": legacy.resources.model_dump(mode="python"),
        "steps": migrated_steps,
    }


def assign_step_ids(data: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(data)
    payload["steps"] = _assign_ids_to_steps(payload.get("steps", []))
    for name, submacro in payload.get("submacros", {}).items():
        submacro["steps"] = _assign_ids_to_steps(submacro.get("steps", []), prefix=f"submacro_{name}")
    return payload


def resolve_retry_policy(step_retry: Any, policies: dict[str, RetryPolicySpec]) -> RetryPolicySpec:
    if isinstance(step_retry, RetryPolicySpec):
        return step_retry
    if isinstance(step_retry, str):
        return policies[step_retry]
    if isinstance(step_retry, dict):
        if "policy" in step_retry:
            base = policies[step_retry["policy"]].model_dump(mode="python")
            override = {key: value for key, value in step_retry.items() if key != "policy"}
            base.update(override)
            return RetryPolicySpec.model_validate(base)
        return RetryPolicySpec.model_validate(step_retry)
    return RetryPolicySpec()


def _apply_defaults_to_steps(steps: list[dict[str, Any]], defaults: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        item = copy.deepcopy(step)
        if item.get("timeout_ms") is None and defaults.get("timeout_ms") is not None:
            item["timeout_ms"] = defaults["timeout_ms"]
        if item.get("retry") is None:
            if "retry_policy" in defaults:
                item["retry"] = defaults["retry_policy"]
            elif "retry_attempts" in defaults or "retry_delay_ms" in defaults:
                item["retry"] = {
                    "max_attempts": defaults.get("retry_attempts", 1),
                    "delay_ms": defaults.get("retry_delay_ms", 250),
                }
        if item.get("type") == "if":
            item["then_steps"] = _apply_defaults_to_steps(item.get("then_steps", []), defaults, prefix=f"{prefix}_if_{index}")
            item["else_steps"] = _apply_defaults_to_steps(item.get("else_steps", []), defaults, prefix=f"{prefix}_else_{index}")
        elif item.get("type") == "retry":
            item["steps"] = _apply_defaults_to_steps(item.get("steps", []), defaults, prefix=f"{prefix}_retry_{index}")
        normalized.append(item)
    return normalized


def _assign_ids_to_steps(steps: list[dict[str, Any]], prefix: str = "step") -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        item = copy.deepcopy(step)
        step_type = item.get("type", "step")
        item.setdefault("id", f"{prefix}_{index:03d}_{step_type}")
        item.setdefault("name", item["id"])
        if step_type == "if":
            item["then_steps"] = _assign_ids_to_steps(item.get("then_steps", []), prefix=f"{item['id']}_then")
            item["else_steps"] = _assign_ids_to_steps(item.get("else_steps", []), prefix=f"{item['id']}_else")
        elif step_type == "retry":
            item["steps"] = _assign_ids_to_steps(item.get("steps", []), prefix=f"{item['id']}_retry")
        assigned.append(item)
    return assigned


def _is_legacy_macro(data: dict[str, Any]) -> bool:
    version = str(data.get("schema_version") or "")
    if version.startswith(LEGACY_SCHEMA_VERSION):
        return True
    steps = data.get("steps") or []
    if not steps:
        return False
    first = steps[0]
    return isinstance(first, dict) and "action" in first and "type" not in first


def _load_structured_data(path: Path, raw: str) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(raw)
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(raw) or {}
    raise ValueError(f"Unsupported macro format: {path}")
