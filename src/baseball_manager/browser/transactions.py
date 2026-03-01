"""
Handles add/drop transactions on Yahoo Fantasy Baseball via browser automation.

Add flow:
  1. Search for player on Yahoo's add player page
  2. Click Add (or Add/Drop)
  3. Select the player to drop if roster is full
  4. Confirm

Drop flow:
  1. Navigate to edit roster page
  2. Find player row, click Drop link
  3. Confirm if prompted
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page
    from baseball_manager.browser.yahoo_browser import YahooBrowser

logger = logging.getLogger(__name__)

FANTASY_BASE = "https://baseball.fantasysports.yahoo.com/b1"


class TransactionManager:
    """Executes add/drop transactions on Yahoo Fantasy Baseball."""

    def __init__(self, browser: "YahooBrowser"):
        self.browser = browser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_player(self, add_name: str, drop_name: str | None = None) -> bool:
        """
        Add a free agent.  If drop_name is provided, drop that player
        as part of the same transaction (roster-full scenario).

        Returns True on success, False on failure.
        """
        from baseball_manager.config import LEAGUE_ID

        search_url = (
            f"{FANTASY_BASE}/{LEAGUE_ID}/addplayer"
            f"?pos=ALL&status=A&sort=AR&sdir=1"
            f"&search={add_name.replace(' ', '+')}"
        )

        try:
            logger.info(f"Searching for player to add: {add_name}")
            self.browser.navigate(search_url)
            page = self.browser.page

            page.wait_for_selector(
                "#playerTable, .ysf-player-name, .add-player-row",
                timeout=20000,
            )

            player_row = self._find_player_row(page, add_name)
            if player_row is None:
                logger.error(f"Could not find '{add_name}' in search results")
                self.browser.screenshot(f"add_not_found_{_safe(add_name)}")
                return False

            # Click the Add (or Add/Drop) button for this player
            add_btn = player_row.locator(
                "button:has-text('Add'), a:has-text('Add'), input[value='Add']"
            ).first
            if add_btn.count() == 0 or not add_btn.is_visible():
                logger.error(f"Add button not found for '{add_name}'")
                self.browser.screenshot(f"add_btn_missing_{_safe(add_name)}")
                return False

            add_btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

            # Handle drop selection if roster is full
            if drop_name:
                if not self._select_drop_player(page, drop_name):
                    logger.warning(f"Could not select drop player '{drop_name}'")

            # Confirm the transaction
            for selector in [
                "input[value='Submit']",
                "input[value='Yes, Claim Player']",
                "button:has-text('Submit')",
                "button[type='submit']",
            ]:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    break

            logger.info(
                f"Added {add_name}"
                + (f", dropped {drop_name}" if drop_name else "")
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add '{add_name}': {e}")
            self.browser.screenshot(f"add_error_{_safe(add_name)}")
            return False

    def drop_player(self, drop_name: str) -> bool:
        """
        Drop a player from the roster.
        Returns True on success, False on failure.
        """
        from baseball_manager.config import LEAGUE_ID, MY_TEAM_ID

        roster_url = f"{FANTASY_BASE}/{LEAGUE_ID}/{MY_TEAM_ID}/editroster"

        try:
            logger.info(f"Dropping player: {drop_name}")
            self.browser.navigate(roster_url)
            page = self.browser.page

            page.wait_for_selector(
                "#statTable0, .ysf-roster, table.ysf-player-name",
                timeout=20000,
            )

            player_row = self._find_player_row(page, drop_name)
            if player_row is None:
                logger.error(f"Player not found on roster: {drop_name}")
                return False

            drop_btn = player_row.locator(
                "a:has-text('Drop'), button:has-text('Drop')"
            ).first
            if drop_btn.count() == 0 or not drop_btn.is_visible():
                logger.error(f"Drop link not found for '{drop_name}'")
                self.browser.screenshot(f"drop_btn_missing_{_safe(drop_name)}")
                return False

            drop_btn.click()
            page.wait_for_load_state("networkidle", timeout=20000)

            # Confirm if prompted
            for selector in [
                "input[value='Yes']",
                "button:has-text('Yes')",
                "button:has-text('Confirm')",
                "input[value='Confirm']",
            ]:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    break

            logger.info(f"Dropped {drop_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to drop '{drop_name}': {e}")
            self.browser.screenshot(f"drop_error_{_safe(drop_name)}")
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_player_row(self, page: "Page", name: str) -> "Locator | None":
        """Return the first <tr> containing this player's name, or None."""
        safe_name = name.replace("'", "\\'")
        for selector in [
            f"tr:has(a:text-is('{safe_name}'))",
            f"tr:has-text('{safe_name}')",
        ]:
            try:
                loc = page.locator(selector)
                if loc.count() > 0:
                    return loc.first
            except Exception:
                continue
        return None

    def _select_drop_player(self, page: "Page", drop_name: str) -> bool:
        """
        On an add/drop confirmation page, select the player to drop.
        Yahoo may show a <select> or radio buttons for the drop choice.
        """
        safe_name = drop_name.replace("'", "\\'")

        # Try <select> with the player's name as an option label
        drop_select = page.locator(
            "select[name='drop_player_id'], select[name='drop']"
        ).first
        if drop_select.count() > 0 and drop_select.is_visible():
            try:
                drop_select.select_option(label=drop_name)
                return True
            except Exception:
                pass

        # Try radio buttons in a drop table
        drop_row = self._find_player_row(page, drop_name)
        if drop_row is not None:
            radio = drop_row.locator("input[type='radio'], input[type='checkbox']").first
            if radio.count() > 0 and radio.is_visible():
                radio.check()
                return True

        return False


def _safe(name: str, max_len: int = 20) -> str:
    """Sanitize a player name for use in a filename."""
    return name.replace(" ", "_").replace("'", "")[:max_len]
