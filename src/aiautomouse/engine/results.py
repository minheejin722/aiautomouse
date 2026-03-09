from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class AutomationError(RuntimeError):
    """Base runtime error."""


class EmergencyStopError(AutomationError):
    """Raised when the emergency stop token is triggered."""


class TargetResolutionError(AutomationError):
    """Raised when a target cannot be resolved."""


class ProviderTimeoutError(TargetResolutionError):
    """Raised when a provider.find() call exceeds the configured timeout."""


class ConditionEvaluationError(AutomationError):
    """Raised when a condition fails unexpectedly."""


class ActionExecutionError(AutomationError):
    """Raised when an action cannot be completed."""


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def offset(self, dx: int, dy: int) -> tuple[int, int]:
        center_x, center_y = self.center
        return center_x + dx, center_y + dy

    def to_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


@dataclass
class TargetMatch:
    provider_name: str
    rect: Rect
    confidence: float
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rect"] = self.rect.to_dict()
        return payload


@dataclass
class StepResult:
    step_id: str
    step_type: str
    status: StepStatus
    attempts: int
    duration_ms: int
    step_path: str | None = None
    error: str | None = None
    action_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class MacroRunResult:
    macro_name: str
    status: StepStatus
    duration_ms: int
    steps: list[StepResult] = field(default_factory=list)
    run_id: str | None = None
    error: str | None = None
    failed_step_id: str | None = None
    summary_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro_name": self.macro_name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "run_id": self.run_id,
            "error": self.error,
            "failed_step_id": self.failed_step_id,
            "summary_path": self.summary_path,
            "steps": [step.to_dict() for step in self.steps],
        }
