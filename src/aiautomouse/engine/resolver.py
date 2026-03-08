from __future__ import annotations

from aiautomouse.engine.models import TargetSpec
from aiautomouse.engine.results import TargetResolutionError


class TargetResolver:
    def __init__(self, providers: list[object]) -> None:
        self.providers = providers

    def ordered_provider_names(self) -> list[str]:
        return [provider.name for provider in self.providers]

    def resolve(self, target: TargetSpec, ctx: object):
        if not target.has_any:
            raise TargetResolutionError("Target has no locator data")
        errors: list[str] = []
        for provider in self.providers:
            if not provider.supports(target):
                continue
            if not provider.is_available():
                errors.append(f"{provider.name}: unavailable")
                continue
            try:
                match = provider.find(target, ctx)
            except Exception as exc:  # pragma: no cover - provider-specific failures
                errors.append(f"{provider.name}: {exc}")
                continue
            if match:
                return match
        detail = "; ".join(errors) if errors else "no provider could resolve target"
        raise TargetResolutionError(detail)

