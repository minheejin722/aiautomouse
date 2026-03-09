from __future__ import annotations

import threading

from aiautomouse.engine.context import RuntimeContext
from aiautomouse.engine.models import TargetSpec
from aiautomouse.engine.results import TargetResolutionError


class TargetResolver:
    def __init__(self, providers: list[object], timeout_ms: int = 0) -> None:
        self.providers = providers
        self._timeout_ms = max(0, timeout_ms)

    def ordered_provider_names(self) -> list[str]:
        return [provider.name for provider in self.providers]

    def resolve(self, target: TargetSpec, ctx: RuntimeContext):
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
                match = self._find_with_timeout(provider, target, ctx)
            except _ProviderTimeout:
                timeout_sec = self._timeout_ms / 1000.0
                errors.append(f"{provider.name}: timed out after {timeout_sec:.1f}s")
                continue
            except Exception as exc:  # pragma: no cover - provider-specific failures
                errors.append(f"{provider.name}: {exc}")
                continue
            if match:
                return match
        detail = "; ".join(errors) if errors else "no provider could resolve target"
        raise TargetResolutionError(detail)

    def _find_with_timeout(self, provider, target: TargetSpec, ctx: RuntimeContext):
        if self._timeout_ms <= 0:
            return provider.find(target, ctx)

        result_holder: list = []
        error_holder: list[Exception] = []

        def _worker() -> None:
            try:
                result_holder.append(provider.find(target, ctx))
            except Exception as exc:
                error_holder.append(exc)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout_ms / 1000.0)

        if thread.is_alive():
            raise _ProviderTimeout(provider.name)

        if error_holder:
            raise error_holder[0]

        return result_holder[0] if result_holder else None


class _ProviderTimeout(Exception):
    """Internal sentinel – never leaks outside TargetResolver."""

