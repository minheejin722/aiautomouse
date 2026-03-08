from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aiautomouse.engine.models import MacroSpec, TemplateResourceSpec


@dataclass(frozen=True)
class TemplateAsset:
    reference: str
    path: Path
    metadata: TemplateResourceSpec
    mask_path: Path | None = None


class TemplateStore:
    def __init__(self, root: Path, templates: dict[str, str | TemplateResourceSpec]) -> None:
        self.root = root
        self._templates = templates

    @classmethod
    def from_macro(cls, macro: MacroSpec, macro_path: Path) -> "TemplateStore":
        return cls(macro_path.parent, macro.resources.templates)

    def resolve(self, reference: str) -> Path:
        return self.get(reference).path

    def get(self, reference: str) -> TemplateAsset:
        raw_entry = self._templates.get(reference, reference)
        if isinstance(raw_entry, TemplateResourceSpec):
            inline = raw_entry.model_dump(exclude_none=True, mode="python")
            path_value = raw_entry.path
        elif isinstance(raw_entry, dict):
            inline = dict(raw_entry)
            path_value = str(inline.get("path") or reference)
        else:
            inline = {}
            path_value = str(raw_entry)
        resolved_path = self._resolve_path(path_value)
        sidecar = self._load_sidecar_metadata(resolved_path)
        merged = {**sidecar, **inline, "path": str(resolved_path)}
        merged.setdefault("name", reference)
        metadata = TemplateResourceSpec.model_validate(merged)
        mask_path = self._resolve_mask_path(resolved_path, metadata.mask_path if hasattr(metadata, "mask_path") else None)
        return TemplateAsset(reference=reference, path=resolved_path, metadata=metadata, mask_path=mask_path)

    def _resolve_path(self, reference: str) -> Path:
        path = Path(reference)
        if path.is_absolute():
            return path
        macro_relative = (self.root / path).resolve()
        if macro_relative.exists():
            return macro_relative
        return (Path.cwd() / path).resolve()

    def _load_sidecar_metadata(self, template_path: Path) -> dict[str, Any]:
        candidates = [
            template_path.with_suffix(template_path.suffix + ".template.json"),
            template_path.with_suffix(template_path.suffix + ".template.yaml"),
            template_path.with_suffix(template_path.suffix + ".template.yml"),
            template_path.with_suffix(".template.json"),
            template_path.with_suffix(".template.yaml"),
            template_path.with_suffix(".template.yml"),
        ]
        for candidate in candidates:
            if not candidate.exists():
                continue
            raw = candidate.read_text(encoding="utf-8-sig")
            if candidate.suffix.lower() == ".json":
                return json.loads(raw)
            return yaml.safe_load(raw) or {}
        return {}

    def _resolve_mask_path(self, template_path: Path, explicit: str | None) -> Path | None:
        if explicit:
            resolved = self._resolve_path(explicit)
            return resolved if resolved.exists() else None
        candidates = [
            template_path.with_name(f"{template_path.stem}.mask{template_path.suffix}"),
            template_path.with_name(f"{template_path.stem}_mask{template_path.suffix}"),
            template_path.with_name(f"{template_path.stem}.mask.png"),
            template_path.with_name(f"{template_path.stem}_mask.png"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None
