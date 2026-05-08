from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock

from paper_fetch.runtime import RuntimeContext
from paper_fetch.runtime_playwright import PlaywrightContextManager


class _FakeBrowser:
    def __init__(self, *, headless: bool) -> None:
        self.headless = headless
        self.context_kwargs: list[dict[str, object]] = []
        self.close_count = 0

    def new_context(self, **kwargs):
        self.context_kwargs.append(dict(kwargs))
        return SimpleNamespace(kwargs=dict(kwargs))

    def close(self) -> None:
        self.close_count += 1


class _FakeChromium:
    def __init__(self, manager: "_FakePlaywrightManager") -> None:
        self.manager = manager

    def launch(self, *, headless: bool):
        browser = _FakeBrowser(headless=headless)
        self.manager.browser = browser
        return browser


class _FakePlaywrightManager:
    def __init__(self) -> None:
        self.chromium = _FakeChromium(self)
        self.browser: _FakeBrowser | None = None
        self.stop_count = 0

    def stop(self) -> None:
        self.stop_count += 1


class _FakeSyncPlaywrightSession:
    def __init__(self, managers: list[_FakePlaywrightManager]) -> None:
        self.managers = managers

    def start(self):
        manager = _FakePlaywrightManager()
        self.managers.append(manager)
        return manager


def _fake_playwright_modules(managers: list[_FakePlaywrightManager]) -> dict[str, types.ModuleType]:
    playwright_module = types.ModuleType("playwright")
    sync_api_module = types.ModuleType("playwright.sync_api")
    sync_api_module.sync_playwright = lambda: _FakeSyncPlaywrightSession(managers)
    playwright_module.sync_api = sync_api_module
    return {
        "playwright": playwright_module,
        "playwright.sync_api": sync_api_module,
    }


class RuntimePlaywrightTests(unittest.TestCase):
    def test_playwright_manager_reuses_browser_and_restarts_for_headless_change(self) -> None:
        managers: list[_FakePlaywrightManager] = []
        lifecycle = PlaywrightContextManager()

        with mock.patch.dict(sys.modules, _fake_playwright_modules(managers)):
            first_context = lifecycle.new_context(headless=True, locale="en-US")
            second_context = lifecycle.new_context(headless=True, viewport={"width": 800})
            first_browser = managers[0].browser
            restarted_browser = lifecycle.browser(headless=False)
            lifecycle.close()
            lifecycle.close()

        self.assertEqual(first_context.kwargs, {"locale": "en-US"})
        self.assertEqual(second_context.kwargs, {"viewport": {"width": 800}})
        self.assertEqual(len(managers), 2)
        self.assertIsNotNone(first_browser)
        self.assertEqual(first_browser.close_count, 1)
        self.assertEqual(managers[0].stop_count, 1)
        self.assertIs(restarted_browser, managers[1].browser)
        self.assertFalse(restarted_browser.headless)
        self.assertEqual(restarted_browser.close_count, 1)
        self.assertEqual(managers[1].stop_count, 1)

    def test_runtime_context_delegates_playwright_api_to_lifecycle_manager(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []

        class FakeLifecycle:
            def browser(self, **kwargs):
                calls.append(("browser", dict(kwargs)))
                return "browser"

            def new_context(self, **kwargs):
                calls.append(("new_context", dict(kwargs)))
                return "context"

            def close(self):
                calls.append(("close", {}))

        context = RuntimeContext(env={})
        context._playwright_context_manager = FakeLifecycle()

        self.assertEqual(context.playwright_browser(headless=False), "browser")
        self.assertEqual(context.new_playwright_context(headless=True, locale="en-US"), "context")
        context.close_playwright()

        self.assertEqual(
            calls,
            [
                ("browser", {"headless": False}),
                ("new_context", {"headless": True, "locale": "en-US"}),
                ("close", {}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
