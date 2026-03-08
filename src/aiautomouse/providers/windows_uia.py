from __future__ import annotations

from collections import deque
from typing import Any

from aiautomouse.engine.models import TargetSpec
from aiautomouse.engine.results import Rect, TargetMatch
from aiautomouse.providers.base import LocatorProvider


class WindowsUiaProvider(LocatorProvider):
    name = "windows_uia"
    supported_fields = ("uia",)

    def is_available(self) -> bool:
        try:
            from pywinauto import Desktop  # noqa: F401
        except Exception:
            return False
        return True

    def find(self, target: TargetSpec, ctx: object):
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        root = self._resolve_window(desktop, target.window)
        if root is None:
            return None
        control = root if target.uia is None else self._find_descendant(root, target.uia)
        if control is None:
            return None
        rect = self._extract_rect(control)
        if rect is None:
            return None
        value = self._extract_value(control)
        metadata = {
            "name": self._safe_get(control, "window_text") or self._safe_element(control, "name"),
            "automation_id": self._safe_element(control, "automation_id"),
            "class_name": self._safe_element(control, "class_name"),
            "control_type": self._safe_element(control, "control_type"),
            "value": value,
        }
        return TargetMatch(
            provider_name=self.name,
            rect=rect,
            confidence=1.0,
            text=value or metadata["name"],
            metadata=metadata,
        )

    def _resolve_window(self, desktop: Any, window_spec):
        windows = desktop.windows()
        if not window_spec:
            return windows[0] if windows else None
        title_contains = (window_spec.title_contains or "").lower()
        title = window_spec.title
        class_name = window_spec.class_name
        for window in windows:
            name = str(self._safe_get(window, "window_text") or "")
            element_class_name = str(self._safe_element(window, "class_name") or "")
            if title and name != title:
                continue
            if title_contains and title_contains not in name.lower():
                continue
            if class_name and class_name != element_class_name:
                continue
            return window
        return None

    def _find_descendant(self, root: Any, spec):
        for control in self._walk(root, max_depth=25):
            if self._matches(control, spec):
                return control
        return None

    def _walk(self, root: Any, max_depth: int = 10):
        queue = deque([(root, 0)])
        while queue:
            control, depth = queue.popleft()
            yield control
            if depth >= max_depth:
                continue
            try:
                children = control.children()
            except Exception:
                children = []
            for child in children or []:
                queue.append((child, depth + 1))

    def _matches(self, control: Any, spec) -> bool:
        name = str(self._safe_get(control, "window_text") or self._safe_element(control, "name") or "")
        automation_id = str(self._safe_element(control, "automation_id") or "")
        class_name = str(self._safe_element(control, "class_name") or "")
        control_type = str(self._safe_element(control, "control_type") or "")
        if spec.name and name != spec.name:
            return False
        if spec.name_contains and spec.name_contains.lower() not in name.lower():
            return False
        if spec.automation_id and automation_id != spec.automation_id:
            return False
        if spec.class_name and class_name != spec.class_name:
            return False
        if spec.control_type and control_type != spec.control_type:
            return False
        return True

    def _extract_rect(self, control: Any) -> Rect | None:
        try:
            rectangle = control.rectangle()
        except Exception:
            return None
        return Rect(
            left=int(rectangle.left),
            top=int(rectangle.top),
            width=int(rectangle.right - rectangle.left),
            height=int(rectangle.bottom - rectangle.top),
        )

    def _extract_value(self, control: Any) -> str:
        try:
            iface_value = getattr(control.element_info, "iface_value", None)
            if iface_value is not None:
                return str(iface_value.CurrentValue)
        except Exception:
            pass
        return str(self._safe_get(control, "window_text") or self._safe_element(control, "name") or "")

    def _safe_element(self, control: Any, attribute: str):
        try:
            return getattr(control.element_info, attribute)
        except Exception:
            return None

    def _safe_get(self, control: Any, method_name: str):
        try:
            method = getattr(control, method_name)
            return method() if callable(method) else method
        except Exception:
            return None
