from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aiautomouse.runtime.fs import atomic_write_text


class OverlaySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    duration_ms: int = 900


class CdpSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str = "http://127.0.0.1:9222"


class BrowserSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cdp_url: str | None = None
    launch_on_demand: bool = True
    channel: str | None = "msedge"
    headless: bool = False
    default_timeout_ms: int = 5000
    connect_timeout_ms: int = 1500

    @field_validator("default_timeout_ms", "connect_timeout_ms")
    @classmethod
    def validate_browser_timeouts(cls, value: int) -> int:
        return max(1, value)


class PathsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    snippets_dir: Path = Path("assets/snippets")
    templates_dir: Path = Path("assets/templates")
    macros_dir: Path = Path("macros/samples")
    hotkeys_path: Path = Path("config/hotkeys.yaml")
    logs_dir: Path = Path("logs")
    artifacts_dir: Path = Path("logs/runs")
    schema_path: Path = Path("schemas/macro.schema.json")


class DiagnosticsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    capture_before_after_screenshots: bool = True
    capture_active_window_snapshot: bool = True
    dump_ocr_results: bool = True
    dump_image_match_candidates: bool = True
    replay_log_enabled: bool = True
    max_dump_candidates: int = 10

    @field_validator("max_dump_candidates")
    @classmethod
    def validate_max_dump_candidates(cls, value: int) -> int:
        return max(1, value)


class OcrSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backends: list[str] = Field(default_factory=lambda: ["windows", "tesseract", "easyocr"])
    tesseract_cmd: str | None = None
    easyocr_languages: list[str] = Field(default_factory=lambda: ["en", "ko"])
    easyocr_gpu: bool = False
    rate_limit_ms: int = 150
    cache_size: int = 128


class CaptureSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: str = "mss"

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"mss", "dxcam"}:
            raise ValueError("capture backend must be 'mss' or 'dxcam'")
        return normalized


class UiSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recent_runs_limit: int = 50
    default_macro_mode: str = "dry-run"
    auto_start_hotkeys: bool = False

    @field_validator("recent_runs_limit")
    @classmethod
    def validate_recent_runs_limit(cls, value: int) -> int:
        return max(1, value)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    log_level: str = "INFO"
    poll_interval_ms: int = 250
    overlay: OverlaySettings = Field(default_factory=OverlaySettings)
    cdp: CdpSettings = Field(default_factory=CdpSettings)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    emergency_stop_hotkey: str = "Ctrl+Alt+Pause"
    paths: PathsSettings = Field(default_factory=PathsSettings)
    ocr: OcrSettings = Field(default_factory=OcrSettings)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    ui: UiSettings = Field(default_factory=UiSettings)

    @model_validator(mode="after")
    def normalize_browser_settings(self) -> "AppSettings":
        if not self.browser.cdp_url:
            self.browser.cdp_url = self.cdp.url
        return self

    @property
    def artifacts_dir(self) -> Path:
        return self.paths.artifacts_dir

    @classmethod
    def load(cls, path: str | Path) -> "AppSettings":
        source = Path(path)
        if not source.exists():
            settings = cls.from_dict({})
            settings.save(source)
            return settings
        raw = source.read_text(encoding="utf-8-sig")
        if source.suffix.lower() == ".json":
            data = json.loads(raw or "{}")
        else:
            data = yaml.safe_load(raw) or {}
        settings = cls.model_validate(data)
        settings.ensure_directories()
        return settings

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> "AppSettings":
        settings = cls.model_validate(data or {})
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        self.paths.snippets_dir.mkdir(parents=True, exist_ok=True)
        self.paths.templates_dir.mkdir(parents=True, exist_ok=True)
        self.paths.macros_dir.mkdir(parents=True, exist_ok=True)
        self.paths.hotkeys_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        self.paths.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.paths.schema_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        if destination.suffix.lower() == ".json":
            return atomic_write_text(
                destination,
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return atomic_write_text(
            destination,
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
