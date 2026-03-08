from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AmbiguityWarning(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str | None = None
    message: str
    assumption: str | None = None


class SuggestedFallbackStrategy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str | None = None
    message: str
    rationale: str = ""
    suggested_patch: dict[str, Any] = Field(default_factory=dict)


class RequiredResourceChecklistItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resource_type: Literal["snippet", "template"]
    resource_id: str
    exists: bool
    required: bool = True
    note: str = ""


class AdapterRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    adapter: Literal["browser", "uia", "ocr", "image"]
    rationale: str
    confidence: float = 0.0


class MacroAuthoringResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_text: str
    macro_json: dict[str, Any]
    ambiguous_step_warnings: list[AmbiguityWarning] = Field(default_factory=list)
    suggested_fallback_strategies: list[SuggestedFallbackStrategy] = Field(default_factory=list)
    required_resources_checklist: list[RequiredResourceChecklistItem] = Field(default_factory=list)
    target_adapter_recommendation: AdapterRecommendation
