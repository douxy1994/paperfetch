"""Browser lifecycle manager.

All Playwright-typed objects returned by this module are launched by CloakBrowser, not stock Playwright.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class PlaywrightUnavailableError(RuntimeError):
    """Legacy error alias for direct browser launch compatibility."""


class _NoopBrowserManager:
    def stop(self) -> None:
        pass


def launch_playwright_chromium(*, headless: bool = True) -> tuple[Any, Any]:
    """Launch a CloakBrowser browser behind the legacy helper name."""

    try:
        import cloakbrowser
    except Exception as exc:
        raise PlaywrightUnavailableError("cloakbrowser is not installed.") from exc

    browser = cloakbrowser.launch(headless=bool(headless), locale="en-US")
    return _NoopBrowserManager(), browser


@dataclass
class BrowserContextManager:
    """Owns a shared CloakBrowser-launched browser for one fetch runtime."""

    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _browser: Any | None = field(default=None, init=False, repr=False)
    _headless: bool | None = field(default=None, init=False, repr=False)

    def browser(self, *, headless: bool = True) -> Any:
        active_headless = bool(headless)
        with self._lock:
            if self._browser is not None and self._headless == active_headless:
                return self._browser
            if self._browser is not None:
                self.close()

            import cloakbrowser

            browser = cloakbrowser.launch(headless=active_headless, locale="en-US")
            self._browser = browser
            self._headless = active_headless
            return browser

    def new_context(self, *, headless: bool = True, **context_kwargs: Any) -> Any:
        with self._lock:
            return self.browser(headless=headless).new_context(**context_kwargs)

    def close(self) -> None:
        with self._lock:
            browser = self._browser
            self._browser = None
            self._headless = None
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    def __del__(self) -> None:  # pragma: no cover - defensive cleanup at GC/interpreter shutdown
        try:
            self.close()
        except Exception:
            pass


PlaywrightContextManager = BrowserContextManager


__all__ = [
    "BrowserContextManager",
    "PlaywrightContextManager",
    "PlaywrightUnavailableError",
    "launch_playwright_chromium",
]
