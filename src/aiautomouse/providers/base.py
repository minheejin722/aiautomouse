from __future__ import annotations

from abc import ABC, abstractmethod

from aiautomouse.engine.models import TargetSpec


class LocatorProvider(ABC):
    name: str = "provider"
    supported_fields: tuple[str, ...] = ()

    def supports(self, target: TargetSpec) -> bool:
        return any(getattr(target, field) is not None for field in self.supported_fields)

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def find(self, target: TargetSpec, ctx: object):
        raise NotImplementedError

