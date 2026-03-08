from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class StructuredEventLogger:
    def __init__(self, path: str | Path, log_level: str = "INFO") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        self.logger = logging.getLogger(f"aiautomouse.run.{self.path.parent.name}")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)
        self.logger.propagate = False

    def emit(self, event_type: str, **payload) -> dict:
        self.sequence += 1
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": self.sequence,
            "event": event_type,
            **payload,
        }
        serialized = json.dumps(event, ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(serialized + "\n")
        self.logger.info(serialized)
        return event

    def close(self) -> None:
        return None
