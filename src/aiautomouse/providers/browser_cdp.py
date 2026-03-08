from __future__ import annotations

from aiautomouse.browser.adapter import PlaywrightBrowserAdapter
from aiautomouse.engine.models import TargetSpec
from aiautomouse.providers.base import LocatorProvider


class BrowserCdpProvider(LocatorProvider):
    name = "browser_cdp"
    supported_fields = ("dom",)

    def __init__(self, adapter: PlaywrightBrowserAdapter | str) -> None:
        if isinstance(adapter, PlaywrightBrowserAdapter):
            self.adapter = adapter
        else:
            self.adapter = PlaywrightBrowserAdapter(cdp_url=adapter)

    def is_available(self) -> bool:
        return self.adapter.is_available()

    def find(self, target: TargetSpec, ctx: object):
        return self.adapter.find_target(target, ctx)
