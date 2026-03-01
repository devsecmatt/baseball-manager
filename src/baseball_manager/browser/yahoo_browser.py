"""
Base browser class for Yahoo Fantasy Baseball automation via Playwright.

Cookie storage uses Playwright's native storage_state format, which captures
cookies, localStorage, and sessionStorage in one JSON file.

Usage:
    with YahooBrowser() as browser:
        browser.navigate("https://baseball.fantasysports.yahoo.com/...")
        # interact with page

One-time login:
    YahooBrowser.login()   # opens headed browser, waits for user, saves cookies
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root is four levels up from this file
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
COOKIES_FILE = _ROOT / ".playwright_cookies.json"
SCREENSHOTS_DIR = _ROOT / "logs" / "screenshots"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class YahooBrowser:
    """Persistent browser session with Yahoo cookie management."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context = None
        self.page = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "YahooBrowser":
        """Open browser and load saved cookies if present."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()

        storage_state = str(COOKIES_FILE) if COOKIES_FILE.exists() else None

        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self.context = self._browser.new_context(
            storage_state=storage_state,
            user_agent=_USER_AGENT,
        )
        self.page = self.context.new_page()
        return self

    def close(self):
        """Close browser and release resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser close: {e}")
        finally:
            self.page = None
            self.context = None
            self._browser = None
            self._playwright = None

    def __enter__(self) -> "YahooBrowser":
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # One-time login (headed)
    # ------------------------------------------------------------------

    @staticmethod
    def login():
        """
        Open a headed browser window for the user to log in to Yahoo.
        Saves the session to .playwright_cookies.json when done.
        """
        from playwright.sync_api import sync_playwright

        print("Opening headed browser for Yahoo login...")
        print()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(user_agent=_USER_AGENT)
            page = context.new_page()

            page.goto(
                "https://baseball.fantasysports.yahoo.com",
                wait_until="networkidle",
                timeout=30000,
            )

            print("Please log in to Yahoo in the browser window.")
            print(
                "After logging in, navigate to your team page so we can confirm access."
            )
            print()
            input("Press Enter when you are logged in and can see your team roster... ")

            context.storage_state(path=str(COOKIES_FILE))
            print(f"Session saved to {COOKIES_FILE}")

            page.close()
            context.close()
            browser.close()

    # ------------------------------------------------------------------
    # Auth check
    # ------------------------------------------------------------------

    def is_logged_in(self) -> bool:
        """
        Return True if the current session is authenticated on Yahoo.
        Checks for presence of the account menu element.
        """
        if self.page is None:
            return False
        try:
            self.page.goto(
                "https://www.yahoo.com",
                wait_until="networkidle",
                timeout=20000,
            )
            # Account menu appears when logged in; login link appears when not
            account = self.page.locator(
                "#ybarAccountMenu, [data-ylk*='acct'], .ybar-user-name"
            )
            return account.count() > 0
        except Exception as e:
            logger.debug(f"is_logged_in check failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------

    def navigate(self, url: str, timeout: int = 30000):
        """Navigate to URL and wait for network to go idle."""
        self.page.goto(url, wait_until="networkidle", timeout=timeout)

    def screenshot(self, name: str) -> str:
        """Save a PNG screenshot to logs/screenshots/ and return the path."""
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"{timestamp}_{name}.png"
        try:
            self.page.screenshot(path=str(path))
            logger.info(f"Screenshot saved: {path}")
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")
        return str(path)
