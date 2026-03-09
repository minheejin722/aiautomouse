from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from aiautomouse.bootstrap.settings import AppSettings
from aiautomouse.engine.loader import load_macro, load_macro_from_data
from aiautomouse.platform.win32_hotkeys import HotkeyBinding
from aiautomouse.runtime.fs import atomic_write_text


@dataclass(frozen=True)
class FileEntry:
    name: str
    path: Path
    updated_at: datetime


@dataclass(frozen=True)
class RunEntry:
    run_id: str
    macro_name: str
    status: str
    mode: str
    path: Path
    started_at: str | None
    finished_at: str | None
    screenshots: list[Path]
    failed_step_id: str | None = None
    error: str | None = None


class SnippetRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_entries(self) -> list[FileEntry]:
        return sorted(
            [
                FileEntry(
                    name=path.stem,
                    path=path,
                    updated_at=datetime.fromtimestamp(path.stat().st_mtime),
                )
                for path in self.root.glob("*.txt")
            ],
            key=lambda item: item.name.lower(),
        )

    def read(self, name: str) -> str:
        return self._path_for(name).read_text(encoding="utf-8")

    def save(self, name: str, content: str) -> Path:
        path = self._path_for(name)
        return atomic_write_text(path, content, encoding="utf-8")

    def delete(self, name: str) -> None:
        path = self._path_for(name)
        if path.exists():
            path.unlink()

    def _path_for(self, name: str) -> Path:
        normalized = name if name.lower().endswith(".txt") else f"{name}.txt"
        return self.root / normalized


class TemplateRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_entries(self) -> list[FileEntry]:
        supported = ("*.png", "*.jpg", "*.jpeg", "*.bmp")
        entries: list[FileEntry] = []
        for pattern in supported:
            for path in self.root.glob(pattern):
                entries.append(
                    FileEntry(
                        name=path.stem,
                        path=path,
                        updated_at=datetime.fromtimestamp(path.stat().st_mtime),
                    )
                )
        return sorted(entries, key=lambda item: item.name.lower())

    def import_file(self, source: str | Path, name: str | None = None) -> Path:
        source_path = Path(source)
        target_name = name or source_path.name
        if not Path(target_name).suffix:
            target_name = f"{target_name}{source_path.suffix or '.png'}"
        destination = self.root / target_name
        destination.write_bytes(source_path.read_bytes())
        return destination

    def save_bytes(self, name: str, content: bytes, suffix: str = ".png") -> Path:
        filename = name if Path(name).suffix else f"{name}{suffix}"
        path = self.root / filename
        path.write_bytes(content)
        return path

    def delete(self, name: str) -> None:
        path = self._resolve(name)
        if path.exists():
            path.unlink()

    def _resolve(self, name: str) -> Path:
        direct = self.root / name
        if direct.exists():
            return direct
        for candidate in self.root.glob(f"{name}.*"):
            return candidate
        return direct


class MacroRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_entries(self) -> list[FileEntry]:
        entries: list[FileEntry] = []
        for pattern in ("*.json", "*.yaml", "*.yml"):
            for path in self.root.glob(pattern):
                entries.append(
                    FileEntry(
                        name=path.stem,
                        path=path,
                        updated_at=datetime.fromtimestamp(path.stat().st_mtime),
                    )
                )
        return sorted(entries, key=lambda item: item.name.lower())

    def read_text(self, path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8-sig")

    def save_text(self, name: str, content: str, extension: str = ".json") -> Path:
        extension = extension if extension.startswith(".") else f".{extension}"
        filename = name if Path(name).suffix else f"{name}{extension}"
        path = self.root / filename
        return atomic_write_text(path, content, encoding="utf-8")

    def delete(self, path: str | Path) -> None:
        target = Path(path)
        if target.exists():
            target.unlink()

    def validate_text(self, content: str, suffix: str) -> dict[str, Any]:
        if suffix.lower() == ".json":
            data = json.loads(content)
        else:
            data = yaml.safe_load(content) or {}
        macro = load_macro_from_data(data)
        return macro.model_dump(mode="json")

    def load_macro(self, path: str | Path):
        return load_macro(path)


class HotkeyConfigRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save_bindings([])

    def load_bindings(self) -> list[HotkeyBinding]:
        data = yaml.safe_load(self.path.read_text(encoding="utf-8-sig")) or {}
        return [HotkeyBinding(**item) for item in data.get("bindings", [])]

    def save_bindings(self, bindings: list[HotkeyBinding]) -> Path:
        payload = {
            "bindings": [
                {
                    "hotkey": binding.hotkey,
                    "macro": binding.macro,
                    "mode": binding.mode,
                }
                for binding in bindings
            ]
        }
        return atomic_write_text(self.path, yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def upsert_binding(self, binding: HotkeyBinding) -> Path:
        bindings = self.load_bindings()
        updated = [item for item in bindings if Path(item.macro).resolve() != Path(binding.macro).resolve()]
        updated.append(binding)
        return self.save_bindings(updated)

    def remove_binding_for_macro(self, macro_path: str | Path) -> Path:
        resolved = Path(macro_path).resolve()
        bindings = [item for item in self.load_bindings() if Path(item.macro).resolve() != resolved]
        return self.save_bindings(bindings)


class RunHistoryRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_runs(self, limit: int = 50) -> list[RunEntry]:
        runs: list[RunEntry] = []
        for run_dir in self.root.iterdir():
            if not run_dir.is_dir():
                continue
            entry = self._read_run(run_dir)
            if entry is not None:
                runs.append(entry)
        runs.sort(key=lambda item: item.started_at or "", reverse=True)
        return runs[:limit]

    def read_events_text(self, run_dir: str | Path) -> str:
        events_path = Path(run_dir) / "events.jsonl"
        if not events_path.exists():
            return ""
        return events_path.read_text(encoding="utf-8")

    def _read_run(self, run_dir: Path) -> RunEntry | None:
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            return None
        macro_name = run_dir.name
        status = "unknown"
        mode = "unknown"
        started_at = None
        finished_at = None
        failed_step_id = None
        error = None
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("event") == "macro_started":
                    macro_name = str(event.get("macro") or macro_name)
                    mode = str(event.get("mode") or mode)
                    started_at = event.get("timestamp")
                elif event.get("event") == "macro_finished":
                    status = str(event.get("status") or status)
                    finished_at = event.get("timestamp")
                    failed_step_id = event.get("failed_step_id") or failed_step_id
                    error = event.get("error") or error
        summary_path = run_dir / "summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            failed_step_id = summary.get("failed_step_id") or failed_step_id
            error = summary.get("error") or error
        screenshots = sorted((run_dir / "screenshots").glob("*")) if (run_dir / "screenshots").exists() else []
        return RunEntry(
            run_id=run_dir.name,
            macro_name=macro_name,
            status=status,
            mode=mode,
            path=run_dir,
            started_at=started_at,
            finished_at=finished_at,
            screenshots=screenshots,
            failed_step_id=failed_step_id,
            error=error,
        )


class Workspace:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.snippets = SnippetRepository(settings.paths.snippets_dir)
        self.templates = TemplateRepository(settings.paths.templates_dir)
        self.macros = MacroRepository(settings.paths.macros_dir)
        self.hotkeys = HotkeyConfigRepository(settings.paths.hotkeys_path)
        self.runs = RunHistoryRepository(settings.paths.artifacts_dir)

    def update_settings(self, settings: AppSettings) -> None:
        """Reconfigure repositories in-place without replacing the Workspace instance."""
        self.settings = settings
        self.snippets = SnippetRepository(settings.paths.snippets_dir)
        self.templates = TemplateRepository(settings.paths.templates_dir)
        self.macros = MacroRepository(settings.paths.macros_dir)
        self.hotkeys = HotkeyConfigRepository(settings.paths.hotkeys_path)
        self.runs = RunHistoryRepository(settings.paths.artifacts_dir)
