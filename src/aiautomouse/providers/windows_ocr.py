from __future__ import annotations

import asyncio
import io
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from aiautomouse.engine.models import OcrTextLocatorSpec, TargetSpec
from aiautomouse.engine.results import Rect
from aiautomouse.platform.screen_capture import CaptureFrame
from aiautomouse.providers.base import LocatorProvider
from aiautomouse.providers.ocr_common import (
    OcrQuery,
    OcrRateLimiter,
    OcrResultCache,
    OcrTextResult,
    expand_rect,
    normalize_ocr_text,
    select_best_ocr_result,
)
from aiautomouse.runtime.fs import atomic_write_json


class OcrBackend(ABC):
    name: str = "ocr"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def recognize(self, frame: CaptureFrame) -> list[OcrTextResult]:
        raise NotImplementedError


class WinSdkOcrBackend(OcrBackend):
    name = "windows"

    def is_available(self) -> bool:
        try:
            from winsdk.windows.media.ocr import OcrEngine  # noqa: F401
            from winsdk.windows.storage.streams import InMemoryRandomAccessStream  # noqa: F401
        except Exception:
            return False
        return True

    def recognize(self, frame: CaptureFrame) -> list[OcrTextResult]:
        lines = self._run_async(self._recognize(frame))
        return [
            OcrTextResult(
                text=line["text"],
                normalized_text=normalize_ocr_text(line["text"]),
                bbox=line["bbox"],
                line_id=line["line_id"],
                confidence=line["confidence"],
                provider=f"ocr:{self.name}",
                screenshot_id=frame.screenshot_id,
            )
            for line in lines
        ]

    async def _recognize(self, frame: CaptureFrame) -> list[dict[str, Any]]:
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        buffer = io.BytesIO()
        frame.image.save(buffer, format="PNG")
        data = buffer.getvalue()

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(data)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return []
        result = await engine.recognize_async(bitmap)
        lines: list[dict[str, Any]] = []
        for index, line in enumerate(result.lines):
            word_rects = [word.bounding_rect for word in line.words]
            if not word_rects:
                continue
            left = min(rect.x for rect in word_rects)
            top = min(rect.y for rect in word_rects)
            right = max(rect.x + rect.width for rect in word_rects)
            bottom = max(rect.y + rect.height for rect in word_rects)
            lines.append(
                {
                    "text": line.text,
                    "bbox": Rect(left=left, top=top, width=right - left, height=bottom - top),
                    "line_id": f"windows:{index}",
                    "confidence": 0.9,
                }
            )
        return lines

    def _run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coroutine)
        finally:
            asyncio.set_event_loop(None)
            loop.close()


class TesseractOcrBackend(OcrBackend):
    name = "tesseract"

    def __init__(self, tesseract_cmd: str | None = None) -> None:
        self.tesseract_cmd = tesseract_cmd

    def is_available(self) -> bool:
        try:
            import pytesseract
        except Exception:
            return False
        executable = self.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd
        if executable:
            candidate = Path(executable)
            if candidate.is_file():
                return True
            if shutil.which(str(executable)):
                return True
        return shutil.which("tesseract") is not None

    def recognize(self, frame: CaptureFrame) -> list[OcrTextResult]:
        import pytesseract

        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        data = pytesseract.image_to_data(frame.image, output_type=pytesseract.Output.DICT)
        grouped: dict[str, dict[str, Any]] = {}
        for index, text in enumerate(data.get("text", [])):
            value = str(text or "").strip()
            if not value:
                continue
            confidence = _safe_confidence(data.get("conf", ["0"])[index])
            if confidence <= 0:
                continue
            line_key = ":".join(
                str(data.get(key, [0])[index])
                for key in ("block_num", "par_num", "line_num")
            )
            record = grouped.setdefault(
                line_key,
                {
                    "texts": [],
                    "left": int(data["left"][index]),
                    "top": int(data["top"][index]),
                    "right": int(data["left"][index]) + int(data["width"][index]),
                    "bottom": int(data["top"][index]) + int(data["height"][index]),
                    "confidence_total": 0.0,
                    "count": 0,
                    "order": index,
                },
            )
            record["texts"].append(value)
            record["left"] = min(record["left"], int(data["left"][index]))
            record["top"] = min(record["top"], int(data["top"][index]))
            record["right"] = max(record["right"], int(data["left"][index]) + int(data["width"][index]))
            record["bottom"] = max(record["bottom"], int(data["top"][index]) + int(data["height"][index]))
            record["confidence_total"] += confidence
            record["count"] += 1
        results: list[OcrTextResult] = []
        for line_key, record in sorted(grouped.items(), key=lambda item: item[1]["order"]):
            text = " ".join(record["texts"]).strip()
            results.append(
                OcrTextResult(
                    text=text,
                    normalized_text=normalize_ocr_text(text),
                    bbox=Rect(
                        left=record["left"],
                        top=record["top"],
                        width=record["right"] - record["left"],
                        height=record["bottom"] - record["top"],
                    ),
                    line_id=f"tesseract:{line_key}",
                    confidence=record["confidence_total"] / max(1, record["count"]),
                    provider=f"ocr:{self.name}",
                    screenshot_id=frame.screenshot_id,
                )
            )
        return results


class EasyOcrBackend(OcrBackend):
    name = "easyocr"

    def __init__(self, languages: list[str], gpu: bool = False) -> None:
        self.languages = languages
        self.gpu = gpu
        self._reader = None

    def is_available(self) -> bool:
        try:
            import easyocr  # noqa: F401
        except Exception:
            return False
        return True

    def recognize(self, frame: CaptureFrame) -> list[OcrTextResult]:
        import easyocr
        import numpy

        if self._reader is None:
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu, verbose=False)
        results: list[OcrTextResult] = []
        for index, (box, text, confidence) in enumerate(self._reader.readtext(numpy.array(frame.image))):
            if not text:
                continue
            left = int(min(point[0] for point in box))
            top = int(min(point[1] for point in box))
            right = int(max(point[0] for point in box))
            bottom = int(max(point[1] for point in box))
            results.append(
                OcrTextResult(
                    text=text,
                    normalized_text=normalize_ocr_text(text),
                    bbox=Rect(left=left, top=top, width=right - left, height=bottom - top),
                    line_id=f"easyocr:{index}",
                    confidence=float(confidence),
                    provider=f"ocr:{self.name}",
                    screenshot_id=frame.screenshot_id,
                )
            )
        return results


class WindowsOcrProvider(LocatorProvider):
    name = "ocr"
    supported_fields = ("ocr_text",)

    def __init__(
        self,
        backends: list[str | OcrBackend] | None = None,
        tesseract_cmd: str | None = None,
        easyocr_languages: list[str] | None = None,
        easyocr_gpu: bool = False,
        rate_limit_ms: int = 150,
        cache_size: int = 128,
    ) -> None:
        self.backends: list[OcrBackend] = []
        for backend_name in backends or ["windows", "tesseract", "easyocr"]:
            if isinstance(backend_name, OcrBackend):
                self.backends.append(backend_name)
                continue
            normalized = str(backend_name).lower()
            if normalized == "windows":
                self.backends.append(WinSdkOcrBackend())
            elif normalized == "tesseract":
                self.backends.append(TesseractOcrBackend(tesseract_cmd=tesseract_cmd))
            elif normalized == "easyocr":
                self.backends.append(EasyOcrBackend(languages=easyocr_languages or ["en"], gpu=easyocr_gpu))
        self.rate_limiter = OcrRateLimiter(rate_limit_ms)
        self.recognition_cache = OcrResultCache(cache_size)
        self.selection_cache = OcrResultCache(cache_size * 2)

    def is_available(self) -> bool:
        return any(backend.is_available() for backend in self.backends)

    def find(self, target: TargetSpec, ctx: object):
        ocr_spec = target.ocr_text
        if ocr_spec is None:
            return None
        query = self._build_query(ocr_spec)
        if not query.text.strip():
            return None
        query_key = self._query_key(target, query)
        capture_kwargs = self._capture_kwargs(target, ocr_spec)
        base_rect, _, _ = ctx.screen_capture.describe_capture_target(**capture_kwargs)
        last_known = ctx.get_last_known_area(query_key)
        if last_known is not None:
            narrowed = expand_rect(last_known, query.last_known_padding, bounds=base_rect)
            narrowed_frame = ctx.screen_capture.capture_frame(region=narrowed.to_dict(), reason="ocr_last_known")
            matched = self._search_frame(narrowed_frame, query, query_key, ctx, debug_label="ocr_last_known")
            if matched is not None:
                ctx.remember_last_known_area(query_key, matched.bbox)
                return self._to_target_match(matched, query)
        frame = ctx.screen_capture.capture_frame(reason="ocr", **capture_kwargs)
        matched = self._search_frame(frame, query, query_key, ctx, debug_label="ocr")
        if matched is None:
            return None
        ctx.remember_last_known_area(query_key, matched.bbox)
        return self._to_target_match(matched, query)

    def _search_frame(
        self,
        frame: CaptureFrame,
        query: OcrQuery,
        query_key: str,
        ctx: object,
        *,
        debug_label: str,
    ) -> OcrTextResult | None:
        last_known = ctx.get_last_known_area(query_key)
        relative_last_known = self._to_relative_rect(last_known, frame.rect) if last_known is not None else None
        for backend in self.backends:
            if not backend.is_available():
                continue
            selection_key = f"{backend.name}:{frame.fingerprint()}:{query.signature()}:{last_known.to_dict() if last_known else 'none'}"
            cached_selection = self.selection_cache.get(selection_key)
            if cached_selection is not None:
                return cached_selection
            results = self._recognized_results(backend, frame)
            absolute_results = [self._with_absolute_rect(result, frame.rect) for result in results]
            if hasattr(ctx, "remember_ocr_results"):
                ctx.remember_ocr_results(f"{query_key}:{backend.name}", [result.to_dict() for result in absolute_results])
            if hasattr(ctx.overlay, "show_ocr_results"):
                ctx.overlay.show_ocr_results(absolute_results, label=f"{debug_label}:{backend.name}", status="recognized")
            selection = select_best_ocr_result(results, query, last_known_area=relative_last_known)
            self._write_debug_dump(
                ctx,
                backend=backend,
                frame=frame,
                query=query,
                query_key=query_key,
                results=absolute_results,
                selection=self._with_absolute_rect(selection.result, frame.rect) if selection is not None else None,
                debug_label=debug_label,
            )
            if selection is None:
                continue
            absolute = self._with_absolute_rect(selection.result, frame.rect)
            self.selection_cache.set(selection_key, absolute)
            return absolute
        return None

    def _recognized_results(self, backend: OcrBackend, frame: CaptureFrame) -> list[OcrTextResult]:
        cache_key = f"{backend.name}:{frame.fingerprint()}"
        cached = self.recognition_cache.get(cache_key)
        if cached is not None:
            return cached
        self.rate_limiter.wait()
        results = backend.recognize(frame)
        self.recognition_cache.set(cache_key, results)
        return results

    def _capture_kwargs(self, target: TargetSpec, ocr_spec: OcrTextLocatorSpec) -> dict[str, Any]:
        if target.region is not None:
            return {"region": target.region}
        if ocr_spec.monitor_index is not None:
            return {"monitor_index": ocr_spec.monitor_index}
        if target.window is not None:
            return {"window": target.window}
        return {}

    def _build_query(self, spec: OcrTextLocatorSpec) -> OcrQuery:
        return OcrQuery(
            text=str(spec.text or ""),
            match_mode=spec.match_mode,
            case_sensitive=spec.case_sensitive,
            collapse_whitespace=spec.collapse_whitespace,
            fuzzy_threshold=spec.fuzzy_threshold,
            anchor_text=spec.anchor_text,
            anchor_match_mode=spec.anchor_match_mode,
            anchor_relative=spec.anchor_relative,
            anchor_max_distance=spec.anchor_max_distance,
            selection_policy=spec.selection_policy,
            last_known_padding=spec.last_known_padding,
        )

    def _query_key(self, target: TargetSpec, query: OcrQuery) -> str:
        window = target.window.model_dump(mode="python") if target.window else None
        region = target.region.model_dump(mode="python") if hasattr(target.region, "model_dump") else target.region
        return str(
            {
                "query": query.signature(),
                "window": window,
                "region": region,
            }
        )

    def _with_absolute_rect(self, result: OcrTextResult, origin: Rect) -> OcrTextResult:
        return OcrTextResult(
            text=result.text,
            normalized_text=result.normalized_text,
            bbox=Rect(
                left=origin.left + result.bbox.left,
                top=origin.top + result.bbox.top,
                width=result.bbox.width,
                height=result.bbox.height,
            ),
            line_id=result.line_id,
            confidence=result.confidence,
            provider=result.provider,
            screenshot_id=result.screenshot_id,
        )

    def _to_relative_rect(self, rect: Rect, origin: Rect) -> Rect:
        return Rect(
            left=rect.left - origin.left,
            top=rect.top - origin.top,
            width=rect.width,
            height=rect.height,
        )

    def _to_target_match(self, result: OcrTextResult, query: OcrQuery):
        match = result.to_target_match()
        match.metadata.update(
            {
                "query": query.text,
                "match_mode": query.match_mode,
                "selection_policy": query.selection_policy,
                "fallback_ready": True,
            }
        )
        return match

    def _write_debug_dump(
        self,
        ctx: object,
        *,
        backend: OcrBackend,
        frame: CaptureFrame,
        query: OcrQuery,
        query_key: str,
        results: list[OcrTextResult],
        selection: OcrTextResult | None,
        debug_label: str,
    ) -> None:
        diagnostics = getattr(getattr(ctx, "settings", None), "diagnostics", None)
        if diagnostics is not None and not diagnostics.dump_ocr_results:
            return
        if not hasattr(ctx, "artifacts"):
            return
        slug = _slug(f"{backend.name}_{frame.screenshot_id}_{debug_label}")
        destination = ctx.artifacts.debug_path("ocr", f"{slug}.json")
        atomic_write_json(
            destination,
            {
                "backend": backend.name,
                "query": query.text,
                "query_signature": query.signature(),
                "query_key": query_key,
                "debug_label": debug_label,
                "screenshot_id": frame.screenshot_id,
                "capture_rect": frame.rect.to_dict(),
                "result_count": len(results),
                "results": [result.to_dict() for result in results],
                "selected": selection.to_dict() if selection is not None else None,
            },
        )


def _safe_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        return 0.0
    if value < 0:
        return 0.0
    return min(1.0, value / 100.0 if value > 1 else value)


def _slug(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("_") or "ocr"
