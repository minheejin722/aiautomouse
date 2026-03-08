from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | Path, content: str, *, encoding: str = "utf-8") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding=encoding,
        delete=False,
        dir=str(destination.parent),
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        Path(handle.name).replace(destination)
    finally:
        if Path(handle.name).exists():
            Path(handle.name).unlink(missing_ok=True)
    return destination


def atomic_write_json(path: str | Path, payload: Any, *, encoding: str = "utf-8", ensure_ascii: bool = False) -> Path:
    return atomic_write_text(
        path,
        json.dumps(payload, indent=2, ensure_ascii=ensure_ascii),
        encoding=encoding,
    )
