from __future__ import annotations

import time

from aiautomouse.engine.models import TargetSpec
from aiautomouse.engine.resolver import TargetResolver
from aiautomouse.engine.results import Rect, TargetMatch, TargetResolutionError

import pytest


class StubProvider:
    def __init__(self, name, result=None, delay=0):
        self.name = name
        self.result = result
        self.delay = delay
        self.calls = 0

    def supports(self, target):
        return True

    def is_available(self):
        return True

    def find(self, target, ctx):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.result


def test_resolver_timeout_skips_slow_provider():
    """A provider that exceeds the timeout is skipped, and the next provider is tried."""
    slow = StubProvider("slow_provider", delay=2.0, result=TargetMatch("slow_provider", Rect(0, 0, 1, 1), 1.0))
    fast = StubProvider(
        "fast_provider",
        result=TargetMatch("fast_provider", Rect(10, 20, 30, 40), 1.0),
    )
    resolver = TargetResolver([slow, fast], timeout_ms=200)

    result = resolver.resolve(TargetSpec(dom={"css": "input"}), ctx=object())

    assert result.provider_name == "fast_provider"
    # The slow provider's thread was started but the resolver didn't wait for it.
    assert slow.calls == 1
    assert fast.calls == 1


def test_resolver_timeout_all_providers_timeout():
    """When all providers time out, a TargetResolutionError is raised with timeout details."""
    slow1 = StubProvider("provider_a", delay=2.0)
    slow2 = StubProvider("provider_b", delay=2.0)
    resolver = TargetResolver([slow1, slow2], timeout_ms=100)

    with pytest.raises(TargetResolutionError) as exc_info:
        resolver.resolve(TargetSpec(dom={"css": "input"}), ctx=object())

    assert "timed out" in str(exc_info.value)
    assert "provider_a" in str(exc_info.value)
    assert "provider_b" in str(exc_info.value)


def test_resolver_no_timeout_by_default():
    """Without timeout_ms, provider.find() is called directly (no threading overhead)."""
    provider = StubProvider(
        "direct",
        result=TargetMatch("direct", Rect(1, 2, 3, 4), 1.0),
    )
    resolver = TargetResolver([provider])

    result = resolver.resolve(TargetSpec(dom={"css": "input"}), ctx=object())

    assert result.provider_name == "direct"
    assert provider.calls == 1


def test_resolver_timeout_preserves_provider_order():
    """Existing test_resolver_order behavior is preserved with timeout_ms."""
    first = StubProvider("browser_cdp", result=None)
    second = StubProvider(
        "windows_uia",
        result=TargetMatch("windows_uia", Rect(1, 2, 3, 4), 1.0),
    )
    third = StubProvider("windows_ocr", result=None)
    resolver = TargetResolver([first, second, third], timeout_ms=5000)

    result = resolver.resolve(TargetSpec(dom={"css": "input"}), ctx=object())

    assert resolver.ordered_provider_names() == ["browser_cdp", "windows_uia", "windows_ocr"]
    assert result.provider_name == "windows_uia"
    assert first.calls == 1
    assert second.calls == 1
    assert third.calls == 0
