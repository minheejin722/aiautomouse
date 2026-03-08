from __future__ import annotations

from pathlib import Path

from aiautomouse.engine.models import MacroSpec


class SnippetStore:
    def __init__(self, root: Path, snippets: dict[str, str]) -> None:
        self.root = root
        self._paths = snippets

    @classmethod
    def from_macro(cls, macro: MacroSpec, macro_path: Path) -> "SnippetStore":
        return cls(macro_path.parent, macro.resources.snippets)

    def get(self, name: str) -> str:
        if name not in self._paths:
            raise KeyError(f"Unknown snippet: {name}")
        path = self._resolve_path(self._paths[name])
        return path.read_text(encoding="utf-8")

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            return candidate
        macro_relative = (self.root / candidate).resolve()
        if macro_relative.exists():
            return macro_relative
        cwd_relative = (Path.cwd() / candidate).resolve()
        return cwd_relative
