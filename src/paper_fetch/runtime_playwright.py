"""Playwright lifecycle management for runtime contexts."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlaywrightContextManager:
    """Owns a shared Playwright Chromium browser for one fetch runtime."""

    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _playwright_manager: Any | None = field(default=None, init=False, repr=False)
    _browser: Any | None = field(default=None, init=False, repr=False)
    _headless: bool | None = field(default=None, init=False, repr=False)

    def browser(self, *, headless: bool = True) -> Any:
        active_headless = bool(headless)
        with self._lock:
            if self._browser is not None and self._headless == active_headless:
                return self._browser
            if self._browser is not None or self._playwright_manager is not None:
                self.close()

            from playwright.sync_api import sync_playwright

            manager = sync_playwright().start()
            try:
                browser = manager.chromium.launch(headless=active_headless)
            except Exception:
                try:
                    manager.stop()
                finally:
                    pass
                raise
            self._playwright_manager = manager
            self._browser = browser
            self._headless = active_headless
            return browser

    def new_context(self, *, headless: bool = True, **context_kwargs: Any) -> Any:
        with self._lock:
            return self.browser(headless=headless).new_context(**context_kwargs)

    def close(self) -> None:
        with self._lock:
            browser = self._browser
            manager = self._playwright_manager
            self._browser = None
            self._playwright_manager = None
            self._headless = None
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if manager is not None:
                try:
                    manager.stop()
                except Exception:
                    pass

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup at GC/interpreter shutdown
        try:
            self.close()
        except Exception:
            pass


__all__ = ["PlaywrightContextManager"]
