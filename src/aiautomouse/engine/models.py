from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CURRENT_SCHEMA_VERSION = "2.0"
LEGACY_SCHEMA_VERSION = "1.0"

JsonPrimitive: TypeAlias = str | int | float | bool | None


class RetryPolicySpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_attempts: int = 1
    delay_ms: int = 250
    backoff_multiplier: float = 1.0

    @field_validator("max_attempts")
    @classmethod
    def validate_attempts(cls, value: int) -> int:
        return max(1, value)

    @field_validator("delay_ms")
    @classmethod
    def validate_delay(cls, value: int) -> int:
        return max(0, value)

    @field_validator("backoff_multiplier")
    @classmethod
    def validate_backoff(cls, value: float) -> float:
        return max(1.0, value)


RetryPolicyInput: TypeAlias = str | RetryPolicySpec | None


class OffsetSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: int = 0
    y: int = 0

    @classmethod
    def from_any(cls, value: "OffsetSpec | list[int] | tuple[int, int] | None") -> "OffsetSpec":
        if value is None:
            return cls()
        if isinstance(value, OffsetSpec):
            return value
        if isinstance(value, dict):
            return cls(x=int(value.get("x", 0)), y=int(value.get("y", 0)))
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return cls(x=int(value[0]), y=int(value[1]))
        raise ValueError("offset must be a pair of integers")


class PaddingSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0


class RegionSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    left: int | str | None = None
    top: int | str | None = None
    width: int | str | None = None
    height: int | str | None = None
    ref: str | None = None
    region_ref: str | None = None
    padding: int | PaddingSpec | None = None

    @model_validator(mode="after")
    def validate_region(self) -> "RegionSpec":
        has_explicit = all(
            value is not None for value in (self.left, self.top, self.width, self.height)
        )
        if not has_explicit and not self.ref and not self.region_ref:
            raise ValueError("region requires explicit coordinates, ref, or region_ref")
        return self


RegionInput: TypeAlias = str | RegionSpec | None


class WindowLocatorSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    title_contains: str | None = None
    class_name: str | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "WindowLocatorSpec":
        if not any((self.title, self.title_contains, self.class_name)):
            raise ValueError("window locator requires title, title_contains, or class_name")
        return self


class DomLocatorSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    name: str | None = None
    css: str | None = None
    selector: str | None = None
    xpath: str | None = None
    text: str | None = None
    placeholder: str | None = None
    label: str | None = None
    test_id: str | None = None
    title_contains: str | None = None
    url_contains: str | None = None
    context_index: int | None = None
    page_index: int | None = None
    nth: int = 0
    wait_for: Literal["attached", "visible", "hidden", "detached"] = "visible"
    require_enabled: bool = False
    require_stable: bool = False
    wait_for_network_idle: bool = False
    timeout_ms: int | None = None

    @field_validator("context_index", "page_index", "nth", "timeout_ms")
    @classmethod
    def validate_non_negative_dom_ints(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, value)

    @model_validator(mode="after")
    def validate_dom(self) -> "DomLocatorSpec":
        if not any(
            (
                self.role,
                self.css,
                self.selector,
                self.xpath,
                self.text,
                self.placeholder,
                self.label,
                self.test_id,
            )
        ):
            raise ValueError(
                "dom locator requires role, css, selector, xpath, text, placeholder, label, or test_id"
            )
        return self


class UiaLocatorSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    name_contains: str | None = None
    automation_id: str | None = None
    class_name: str | None = None
    control_type: str | None = None

    @model_validator(mode="after")
    def validate_uia(self) -> "UiaLocatorSpec":
        if not any((self.name, self.name_contains, self.automation_id, self.class_name, self.control_type)):
            raise ValueError(
                "uia locator requires name, name_contains, automation_id, class_name, or control_type"
            )
        return self


class OcrTextLocatorSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    case_sensitive: bool = False
    match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    collapse_whitespace: bool = True
    fuzzy_threshold: float = 0.75
    anchor_text: str | None = None
    anchor_match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    anchor_relative: Literal["any", "left_of", "right_of", "above", "below", "near"] = "any"
    anchor_max_distance: int = 400
    selection_policy: Literal["best_match", "highest_confidence", "first", "last_known_area", "nearest_anchor"] = "best_match"
    monitor_index: int | None = None
    last_known_padding: int = 96
    fallback_template_id: str | None = None
    fallback_template_path: str | None = None
    fallback_confidence: float | None = None

    @field_validator("fuzzy_threshold")
    @classmethod
    def validate_fuzzy_threshold(cls, value: float) -> float:
        return min(1.0, max(0.0, value))

    @field_validator("anchor_max_distance", "last_known_padding")
    @classmethod
    def validate_non_negative_int(cls, value: int) -> int:
        return max(0, value)

    @field_validator("monitor_index")
    @classmethod
    def validate_monitor_index(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, value)


class TemplateLocatorSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str | None = None
    template_id: str | None = None
    confidence: float | None = None
    search_region_hint: RegionInput = None
    monitor_index: int | None = None
    use_grayscale: bool | None = None
    use_mask: bool | None = None
    multi_scale: bool | None = None
    scales: list[float] = Field(default_factory=list)
    top_n: int | None = None
    preferred_theme: str | None = None
    preferred_dpi: int | None = None
    click_offset: OffsetSpec | list[int] | tuple[int, int] | None = None
    last_known_padding: int | None = None

    @model_validator(mode="after")
    def validate_template(self) -> "TemplateLocatorSpec":
        if not any((self.path, self.template_id)):
            raise ValueError("template locator requires path or template_id")
        return self

    @field_validator("monitor_index", "preferred_dpi", "last_known_padding", "top_n")
    @classmethod
    def validate_non_negative_template_ints(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, value)

    @field_validator("scales")
    @classmethod
    def validate_scales(cls, value: list[float]) -> list[float]:
        return [float(item) for item in value if float(item) > 0]


class TemplateResourceSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    name: str | None = None
    notes: str = ""
    threshold: float | None = None
    preferred_theme: str | None = None
    preferred_dpi: int | None = None
    language_hint: str | None = None
    search_region_hint: RegionInput = None
    click_offset: OffsetSpec | list[int] | tuple[int, int] | None = None
    use_grayscale: bool = True
    use_mask: bool = False
    mask_path: str | None = None
    monitor_index: int | None = None
    multi_scale: bool = True
    scales: list[float] = Field(default_factory=list)
    top_n: int = 10

    @field_validator("preferred_dpi", "monitor_index", "top_n")
    @classmethod
    def validate_non_negative_metadata_ints(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(0, value)

    @field_validator("scales")
    @classmethod
    def validate_metadata_scales(cls, value: list[float]) -> list[float]:
        return [float(item) for item in value if float(item) > 0]


class TargetSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anchor: str | None = None
    window: WindowLocatorSpec | None = None
    dom: DomLocatorSpec | None = None
    uia: UiaLocatorSpec | None = None
    ocr_text: OcrTextLocatorSpec | None = None
    template: TemplateLocatorSpec | None = None
    region: RegionInput = None
    confidence: float = 0.85

    @property
    def has_locator(self) -> bool:
        return any(
            value is not None
            for value in (self.dom, self.uia, self.ocr_text, self.template)
        )

    @property
    def has_any(self) -> bool:
        return self.has_locator or self.window is not None or self.anchor is not None


class AlwaysCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["always"]


class TextExistsCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["text_exists"]
    query: str
    strategy: Literal["dom", "uia", "ocr", "uia_or_ocr", "dom_or_uia_or_ocr"] = "uia_or_ocr"
    window: WindowLocatorSpec | None = None
    region: RegionInput = None
    case_sensitive: bool = False
    anchor: str | None = None
    match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    collapse_whitespace: bool = True
    fuzzy_threshold: float = 0.75
    anchor_text: str | None = None
    anchor_match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    anchor_relative: Literal["any", "left_of", "right_of", "above", "below", "near"] = "any"
    anchor_max_distance: int = 400
    selection_policy: Literal["best_match", "highest_confidence", "first", "last_known_area", "nearest_anchor"] = "best_match"
    monitor_index: int | None = None
    last_known_padding: int = 96
    fallback_template_id: str | None = None
    fallback_template_path: str | None = None
    fallback_confidence: float | None = None


class ImageExistsCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["image_exists"]
    template_id: str | None = None
    template_path: str | None = None
    region: RegionInput = None
    confidence: float = 0.85
    search_region_hint: RegionInput = None
    monitor_index: int | None = None
    use_grayscale: bool | None = None
    use_mask: bool | None = None
    multi_scale: bool | None = None
    scales: list[float] = Field(default_factory=list)
    top_n: int | None = None
    preferred_theme: str | None = None
    preferred_dpi: int | None = None
    last_known_padding: int | None = None

    @model_validator(mode="after")
    def validate_image(self) -> "ImageExistsCondition":
        if not any((self.template_id, self.template_path)):
            raise ValueError("image_exists requires template_id or template_path")
        return self


class RefExistsCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["ref_exists"]
    ref: str


class WindowActiveCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["window_active"]
    title: str | None = None
    title_contains: str | None = None
    class_name: str | None = None


class VariableEqualsCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["variable_equals"]
    name: str
    value: JsonPrimitive


class StepSucceededCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["step_succeeded"]
    step_id: str


class NotCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["not"]
    condition: "ConditionSpec"


class AnyCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["any"]
    conditions: list["ConditionSpec"]


class AllCondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["all"]
    conditions: list["ConditionSpec"]


ConditionSpec: TypeAlias = Annotated[
    AlwaysCondition
    | TextExistsCondition
    | ImageExistsCondition
    | RefExistsCondition
    | WindowActiveCondition
    | VariableEqualsCondition
    | StepSucceededCondition
    | NotCondition
    | AnyCondition
    | AllCondition,
    Field(discriminator="type"),
]


class StepBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    id: str | None = None
    name: str | None = None
    timeout_ms: int | None = None
    retry: RetryPolicyInput = None
    when: ConditionSpec | None = None
    save_as: str | None = None

    @field_validator("timeout_ms")
    @classmethod
    def validate_timeout(cls, value: int | None) -> int | None:
        if value is None:
            return None
        return max(1, value)


class FocusWindowStep(StepBase):
    type: Literal["focus_window"]
    title: str | None = None
    title_contains: str | None = None
    class_name: str | None = None
    anchor: str | None = None

    @model_validator(mode="after")
    def validate_focus(self) -> "FocusWindowStep":
        if not any((self.title, self.title_contains, self.class_name, self.anchor)):
            raise ValueError("focus_window requires title, title_contains, class_name, or anchor")
        return self


class OpenPageStep(StepBase):
    type: Literal["open_page"]
    url: str
    new_tab: bool = True
    new_window: bool = False
    reuse_existing: bool = False
    title_contains: str | None = None
    url_contains: str | None = None
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class FindTextStep(StepBase):
    type: Literal["find_text"]
    query: str
    strategy: Literal["dom", "uia", "ocr", "uia_or_ocr", "dom_or_uia_or_ocr"] = "uia_or_ocr"
    window: WindowLocatorSpec | None = None
    region: RegionInput = None
    case_sensitive: bool = False
    anchor: str | None = None
    confidence: float = 0.85
    match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    collapse_whitespace: bool = True
    fuzzy_threshold: float = 0.75
    anchor_text: str | None = None
    anchor_match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    anchor_relative: Literal["any", "left_of", "right_of", "above", "below", "near"] = "any"
    anchor_max_distance: int = 400
    selection_policy: Literal["best_match", "highest_confidence", "first", "last_known_area", "nearest_anchor"] = "best_match"
    monitor_index: int | None = None
    last_known_padding: int = 96
    fallback_template_id: str | None = None
    fallback_template_path: str | None = None
    fallback_confidence: float | None = None


class FindImageStep(StepBase):
    type: Literal["find_image"]
    template_id: str | None = None
    template_path: str | None = None
    region: RegionInput = None
    confidence: float = 0.85
    search_region_hint: RegionInput = None
    monitor_index: int | None = None
    use_grayscale: bool | None = None
    use_mask: bool | None = None
    multi_scale: bool | None = None
    scales: list[float] = Field(default_factory=list)
    top_n: int | None = None
    preferred_theme: str | None = None
    preferred_dpi: int | None = None
    last_known_padding: int | None = None

    @model_validator(mode="after")
    def validate_find_image(self) -> "FindImageStep":
        if not any((self.template_id, self.template_path)):
            raise ValueError("find_image requires template_id or template_path")
        return self


class ClickRefStep(StepBase):
    type: Literal["click_ref"]
    ref: str
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None


class ClickStep(StepBase):
    type: Literal["click"]
    ref: str | None = None
    x: int | str | None = None
    y: int | str | None = None
    target: TargetSpec | None = None
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None

    @model_validator(mode="after")
    def validate_click(self) -> "ClickStep":
        if self.ref or self.target:
            return self
        if self.x is not None and self.y is not None:
            return self
        raise ValueError("click requires ref, target, or x/y")


class ClickXYStep(StepBase):
    type: Literal["click_xy"]
    x: int | str
    y: int | str


class DoubleClickRefStep(StepBase):
    type: Literal["double_click_ref"]
    ref: str
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None


class DoubleClickStep(StepBase):
    type: Literal["double_click"]
    ref: str | None = None
    x: int | str | None = None
    y: int | str | None = None
    target: TargetSpec | None = None
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None

    @model_validator(mode="after")
    def validate_double_click(self) -> "DoubleClickStep":
        if self.ref or self.target:
            return self
        if self.x is not None and self.y is not None:
            return self
        raise ValueError("double_click requires ref, target, or x/y")


class RightClickRefStep(StepBase):
    type: Literal["right_click_ref"]
    ref: str
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None


class RightClickStep(StepBase):
    type: Literal["right_click"]
    ref: str | None = None
    x: int | str | None = None
    y: int | str | None = None
    target: TargetSpec | None = None
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None

    @model_validator(mode="after")
    def validate_right_click(self) -> "RightClickStep":
        if self.ref or self.target:
            return self
        if self.x is not None and self.y is not None:
            return self
        raise ValueError("right_click requires ref, target, or x/y")


class TypeTextStep(StepBase):
    type: Literal["type_text"]
    text: str
    ref: str | None = None


class PasteSnippetStep(StepBase):
    type: Literal["paste_snippet"]
    snippet_id: str
    ref: str | None = None


class PressKeysStep(StepBase):
    type: Literal["press_keys"]
    keys: str | list[str]


class UploadFilesStep(StepBase):
    type: Literal["upload_files"]
    files: str | list[str]
    ref: str | None = None
    target: TargetSpec | None = None
    allow_file_chooser: bool = True

    @model_validator(mode="after")
    def validate_upload(self) -> "UploadFilesStep":
        if not any((self.ref, self.target)):
            raise ValueError("upload_files requires ref or target")
        return self


class WaitForTextStep(FindTextStep):
    type: Literal["wait_for_text"]


class WaitForImageStep(FindImageStep):
    type: Literal["wait_for_image"]


class VerifyAnyStep(StepBase):
    type: Literal["verify_any"]
    conditions: list[ConditionSpec]


class VerifyTextStep(StepBase):
    type: Literal["verify_text"]
    query: str
    strategy: Literal["dom", "uia", "ocr", "uia_or_ocr", "dom_or_uia_or_ocr"] = "uia_or_ocr"
    window: WindowLocatorSpec | None = None
    region: RegionInput = None
    case_sensitive: bool = False
    anchor: str | None = None
    match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    collapse_whitespace: bool = True
    fuzzy_threshold: float = 0.75
    anchor_text: str | None = None
    anchor_match_mode: Literal["contains", "exact", "regex", "fuzzy"] = "contains"
    anchor_relative: Literal["any", "left_of", "right_of", "above", "below", "near"] = "any"
    anchor_max_distance: int = 400
    selection_policy: Literal["best_match", "highest_confidence", "first", "last_known_area", "nearest_anchor"] = "best_match"
    monitor_index: int | None = None
    last_known_padding: int = 96
    fallback_template_id: str | None = None
    fallback_template_path: str | None = None
    fallback_confidence: float | None = None


class VerifyImageStep(StepBase):
    type: Literal["verify_image"]
    template_id: str | None = None
    template_path: str | None = None
    region: RegionInput = None
    confidence: float = 0.85
    search_region_hint: RegionInput = None
    monitor_index: int | None = None
    use_grayscale: bool | None = None
    use_mask: bool | None = None
    multi_scale: bool | None = None
    scales: list[float] = Field(default_factory=list)
    top_n: int | None = None
    preferred_theme: str | None = None
    preferred_dpi: int | None = None
    last_known_padding: int | None = None

    @model_validator(mode="after")
    def validate_verify_image(self) -> "VerifyImageStep":
        if not any((self.template_id, self.template_path)):
            raise ValueError("verify_image requires template_id or template_path")
        return self


class VerifyAllStep(StepBase):
    type: Literal["verify_all"]
    conditions: list[ConditionSpec]


class IfStep(StepBase):
    type: Literal["if"]
    condition: ConditionSpec
    then_steps: list["StepSpec"]
    else_steps: list["StepSpec"] = Field(default_factory=list)


class RetryBlockStep(StepBase):
    type: Literal["retry"]
    steps: list["StepSpec"]
    policy: RetryPolicyInput = None


class CallSubmacroStep(StepBase):
    type: Literal["call_submacro"]
    submacro: str | None = None
    path: str | None = None
    with_variables: dict[str, JsonPrimitive] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_call(self) -> "CallSubmacroStep":
        if not any((self.submacro, self.path)):
            raise ValueError("call_submacro requires submacro or path")
        return self


class AbortStep(StepBase):
    type: Literal["abort"]
    message: str = "Macro aborted"


class LegacyRetrySpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attempts: int = 1
    delay_ms: int = 250


class LegacyConditionSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str = "always"
    target: TargetSpec | None = None
    value: Any = None
    operator: str = "contains"
    region: RegionInput = None


class LegacyActionSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    target: TargetSpec | None = None
    input: Any = None
    button: str = "left"
    modifiers: list[str] = Field(default_factory=list)
    snippet: str | None = None
    offset: OffsetSpec | list[int] | tuple[int, int] | None = None
    duration_ms: int = 0


class LegacyStepSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    timeout_ms: int = 5000
    retry: LegacyRetrySpec = Field(default_factory=LegacyRetrySpec)
    precondition: LegacyConditionSpec = Field(default_factory=LegacyConditionSpec)
    action: LegacyActionSpec
    postcondition: LegacyConditionSpec = Field(default_factory=LegacyConditionSpec)
    rollback: LegacyActionSpec = Field(default_factory=lambda: LegacyActionSpec(kind="noop"))
    fallback: LegacyActionSpec = Field(default_factory=lambda: LegacyActionSpec(kind="noop"))


class LegacyCompatStep(StepBase):
    type: Literal["legacy_compat"]
    legacy: LegacyStepSpec


StepSpec: TypeAlias = Annotated[
    FocusWindowStep
    | OpenPageStep
    | FindTextStep
    | FindImageStep
    | ClickRefStep
    | ClickStep
    | ClickXYStep
    | DoubleClickRefStep
    | DoubleClickStep
    | RightClickRefStep
    | RightClickStep
    | TypeTextStep
    | PasteSnippetStep
    | PressKeysStep
    | UploadFilesStep
    | WaitForTextStep
    | WaitForImageStep
    | VerifyAnyStep
    | VerifyTextStep
    | VerifyImageStep
    | VerifyAllStep
    | IfStep
    | RetryBlockStep
    | CallSubmacroStep
    | AbortStep
    | LegacyCompatStep,
    Field(discriminator="type"),
]


class MacroResources(BaseModel):
    model_config = ConfigDict(extra="ignore")

    snippets: dict[str, str] = Field(default_factory=dict)
    templates: dict[str, str | TemplateResourceSpec] = Field(default_factory=dict)


class SubmacroSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    variables: dict[str, JsonPrimitive] = Field(default_factory=dict)
    steps: list[StepSpec]


class MacroSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = CURRENT_SCHEMA_VERSION
    name: str
    description: str = ""
    hotkey: str | None = None
    target_profile: str | None = None
    defaults: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, JsonPrimitive] = Field(default_factory=dict)
    resources: MacroResources = Field(default_factory=MacroResources)
    anchors: dict[str, TargetSpec] = Field(default_factory=dict)
    regions: dict[str, RegionSpec] = Field(default_factory=dict)
    retry_policies: dict[str, RetryPolicySpec] = Field(default_factory=dict)
    submacros: dict[str, SubmacroSpec] = Field(default_factory=dict)
    steps: list[StepSpec]

    @model_validator(mode="before")
    @classmethod
    def normalize_submacros(cls, value: Any):
        if not isinstance(value, dict):
            return value
        raw_submacros = value.get("submacros") or {}
        normalized = {}
        for name, raw_submacro in raw_submacros.items():
            if isinstance(raw_submacro, list):
                normalized[name] = {"steps": raw_submacro}
            else:
                normalized[name] = raw_submacro
        if normalized:
            value = dict(value)
            value["submacros"] = normalized
        return value

    @model_validator(mode="after")
    def validate_steps(self) -> "MacroSpec":
        self.schema_version = self.schema_version or CURRENT_SCHEMA_VERSION
        ids = [step.id for step in self._all_steps() if getattr(step, "id", None)]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique")
        return self

    def _all_steps(self) -> list[StepSpec]:
        items: list[StepSpec] = []
        for step in self.steps:
            items.extend(_flatten_step(step))
        for submacro in self.submacros.values():
            for step in submacro.steps:
                items.extend(_flatten_step(step))
        return items


class LegacyMacroSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = LEGACY_SCHEMA_VERSION
    name: str
    description: str = ""
    defaults: dict[str, Any] = Field(default_factory=dict)
    resources: MacroResources = Field(default_factory=MacroResources)
    steps: list[LegacyStepSpec]


def _flatten_step(step: StepSpec) -> list[StepSpec]:
    items = [step]
    if isinstance(step, IfStep):
        for nested in step.then_steps:
            items.extend(_flatten_step(nested))
        for nested in step.else_steps:
            items.extend(_flatten_step(nested))
    elif isinstance(step, RetryBlockStep):
        for nested in step.steps:
            items.extend(_flatten_step(nested))
    return items


IfStep.model_rebuild()
RetryBlockStep.model_rebuild()
AnyCondition.model_rebuild()
AllCondition.model_rebuild()
NotCondition.model_rebuild()
SubmacroSpec.model_rebuild()
