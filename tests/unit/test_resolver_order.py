from __future__ import annotations

from aiautomouse.engine.models import TargetSpec
from aiautomouse.engine.resolver import TargetResolver
from aiautomouse.engine.results import Rect, TargetMatch


class StubProvider:
    def __init__(self, name, result=None):
        self.name = name
        self.result = result
        self.calls = 0

    def supports(self, target):
        return True

    def is_available(self):
        return True

    def find(self, target, ctx):
        self.calls += 1
        return self.result


def test_resolver_preserves_provider_order():
    first = StubProvider("browser_cdp", result=None)
    second = StubProvider(
        "windows_uia",
        result=TargetMatch("windows_uia", Rect(1, 2, 3, 4), 1.0),
    )
    third = StubProvider("windows_ocr", result=None)
    resolver = TargetResolver([first, second, third])

    result = resolver.resolve(TargetSpec(dom={"css": "input"}), ctx=object())

    assert resolver.ordered_provider_names() == ["browser_cdp", "windows_uia", "windows_ocr"]
    assert result.provider_name == "windows_uia"
    assert first.calls == 1
    assert second.calls == 1
    assert third.calls == 0

