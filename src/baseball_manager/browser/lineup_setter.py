"""
Sets the daily lineup on Yahoo Fantasy Baseball via browser automation.

Yahoo's edit roster page has a table where each player row contains a <select>
element for position assignment. We find each player by name, change their
select to the target slot, then click Save.

Edit roster URL:
  https://baseball.fantasysports.yahoo.com/b1/{league_id}/{team_id}/editroster?date={YYYY-MM-DD}
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page
    from baseball_manager.browser.yahoo_browser import YahooBrowser

logger = logging.getLogger(__name__)

FANTASY_BASE = "https://baseball.fantasysports.yahoo.com/b1"


class LineupSetter:
    """Sets the daily lineup by manipulating Yahoo's edit roster page."""

    def __init__(self, browser: "YahooBrowser"):
        self.browser = browser

    def set_lineup(
        self, date_str: str, optimal_slots: dict[str, list[dict]]
    ) -> list[str]:
        """
        Navigate to Yahoo edit roster page for date_str and apply optimal_slots.

        optimal_slots is the direct output of optimize_lineup():
            { "C": [player_dict, ...], "1B": [...], ... }

        Returns a list of human-readable move descriptions (including errors).
        """
        from baseball_manager.config import LEAGUE_ID, MY_TEAM_ID

        url = (
            f"{FANTASY_BASE}/{LEAGUE_ID}/{MY_TEAM_ID}/editroster"
            f"?date={date_str}"
        )

        moves: list[str] = []

        try:
            logger.info(f"Navigating to edit roster: {url}")
            self.browser.navigate(url)
            page = self.browser.page

            # Wait for the roster table
            page.wait_for_selector(
                "#statTable0, .ysf-roster, table.ysf-player-name",
                timeout=20000,
            )

            # Build flat map: player_name -> target_slot
            desired: dict[str, str] = {}
            for slot, players in optimal_slots.items():
                for p in players:
                    name = p.get("name", "")
                    if name:
                        desired[name] = slot

            any_change = False
            for player_name, target_slot in desired.items():
                try:
                    row = self._find_player_row(page, player_name)
                    if row is None:
                        logger.warning(f"Player row not found on page: {player_name}")
                        continue

                    select = row.locator("select").first
                    if select.count() == 0:
                        logger.debug(f"No position select for {player_name} (may be IL/locked)")
                        continue

                    current = select.input_value()
                    if current == target_slot:
                        continue  # already correct

                    select.select_option(target_slot)
                    moves.append(f"  {player_name}: {current} → {target_slot}")
                    any_change = True
                    logger.info(f"Queued move: {player_name} {current} → {target_slot}")

                except Exception as e:
                    err = f"  ERROR moving {player_name}: {e}"
                    moves.append(err)
                    logger.error(err)
                    self.browser.screenshot(f"error_{player_name.replace(' ', '_')[:20]}")

            if any_change:
                self._click_save(page)
            else:
                logger.info("No lineup changes needed; skipping save.")

        except Exception as e:
            logger.error(f"set_lineup failed: {e}")
            self.browser.screenshot("lineup_setter_error")
            raise

        return moves

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_player_row(self, page: "Page", name: str) -> "Locator | None":
        """
        Return the <tr> element containing the player, or None if not found.

        Yahoo renders player names as links inside table rows.  We try a few
        selector patterns to handle different page layouts.
        """
        # Escape single quotes in names like "Shohei Ohtani" (no issue) but
        # names with apostrophes (e.g. "Brendan O'Hara") need care.
        safe_name = name.replace("'", "\\'")

        for selector in [
            f"tr:has(a:text-is('{safe_name}'))",
            f"tr:has-text('{safe_name}')",
        ]:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue

        return None

    def _click_save(self, page: "Page"):
        """Click the Save / Submit button on the edit roster page."""
        save_selectors = [
            "input[value='Save']",
            "input[value='Submit']",
            "button:has-text('Save')",
            "button[type='submit']",
            "#save-roster",
        ]
        for selector in save_selectors:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                page.wait_for_load_state("networkidle", timeout=20000)
                logger.info("Lineup saved.")
                return
        logger.warning("Save button not found — lineup may not have been submitted.")
        self.browser.screenshot("lineup_save_button_missing")
