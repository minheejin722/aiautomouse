from __future__ import annotations

from aiautomouse.engine.models import (
    DomLocatorSpec,
    OcrTextLocatorSpec,
    TargetSpec,
    TemplateLocatorSpec,
    UiaLocatorSpec,
    WindowLocatorSpec,
)


def build_text_target(
    *,
    query: str,
    strategy: str = "uia_or_ocr",
    window: WindowLocatorSpec | None = None,
    region=None,
    anchor: str | None = None,
    case_sensitive: bool = False,
    confidence: float = 0.85,
    match_mode: str = "contains",
    collapse_whitespace: bool = True,
    fuzzy_threshold: float = 0.75,
    anchor_text: str | None = None,
    anchor_match_mode: str = "contains",
    anchor_relative: str = "any",
    anchor_max_distance: int = 400,
    selection_policy: str = "best_match",
    monitor_index: int | None = None,
    last_known_padding: int = 96,
    fallback_template_id: str | None = None,
    fallback_template_path: str | None = None,
    fallback_confidence: float | None = None,
) -> TargetSpec:
    normalized = strategy.lower()
    dom = None
    uia = None
    ocr_text = None
    template = None
    if normalized in {"dom", "dom_or_uia_or_ocr"}:
        dom = DomLocatorSpec(text=query)
    if normalized in {"uia", "uia_or_ocr", "dom_or_uia_or_ocr"}:
        uia = UiaLocatorSpec(name_contains=query)
    if normalized in {"ocr", "uia_or_ocr", "dom_or_uia_or_ocr"}:
        ocr_text = OcrTextLocatorSpec(
            text=query,
            case_sensitive=case_sensitive,
            match_mode=match_mode,
            collapse_whitespace=collapse_whitespace,
            fuzzy_threshold=fuzzy_threshold,
            anchor_text=anchor_text,
            anchor_match_mode=anchor_match_mode,
            anchor_relative=anchor_relative,
            anchor_max_distance=anchor_max_distance,
            selection_policy=selection_policy,
            monitor_index=monitor_index,
            last_known_padding=last_known_padding,
            fallback_template_id=fallback_template_id,
            fallback_template_path=fallback_template_path,
            fallback_confidence=fallback_confidence,
        )
    if fallback_template_id or fallback_template_path:
        template = TemplateLocatorSpec(
            template_id=fallback_template_id,
            path=fallback_template_path,
            confidence=fallback_confidence or confidence,
        )
    return TargetSpec(
        anchor=anchor,
        window=window,
        dom=dom,
        uia=uia,
        ocr_text=ocr_text,
        template=template,
        region=region,
        confidence=confidence,
    )


def build_image_target(
    *,
    template_id: str | None = None,
    template_path: str | None = None,
    region=None,
    confidence: float = 0.85,
    search_region_hint=None,
    monitor_index: int | None = None,
    use_grayscale: bool | None = None,
    use_mask: bool | None = None,
    multi_scale: bool | None = None,
    scales: list[float] | None = None,
    top_n: int | None = None,
    preferred_theme: str | None = None,
    preferred_dpi: int | None = None,
    click_offset=None,
    last_known_padding: int | None = None,
) -> TargetSpec:
    return TargetSpec(
        template=TemplateLocatorSpec(
            template_id=template_id,
            path=template_path,
            confidence=confidence,
            search_region_hint=search_region_hint,
            monitor_index=monitor_index,
            use_grayscale=use_grayscale,
            use_mask=use_mask,
            multi_scale=multi_scale,
            scales=scales or [],
            top_n=top_n,
            preferred_theme=preferred_theme,
            preferred_dpi=preferred_dpi,
            click_offset=click_offset,
            last_known_padding=last_known_padding,
        ),
        region=region,
        confidence=confidence,
    )
