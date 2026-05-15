from __future__ import annotations

from paper_fetch.runtime_browser import BrowserContextManager
from paper_fetch.runtime_playwright import PlaywrightContextManager


def test_runtime_playwright_module_reexports_legacy_manager_alias() -> None:
    assert PlaywrightContextManager is BrowserContextManager
