# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Python 3.14 with a venv at `.venv/`. Always use `.venv/bin/python` and `.venv/bin/bbm`.

```bash
# Install / reinstall dependencies
.venv/bin/pip install -e ".[dev]"

# Run any CLI command
.venv/bin/bbm <command>
```

No uv installed on this machine — use pip + venv directly.

## Running Commands

```bash
.venv/bin/bbm auth                        # OAuth flow (one-time)
.venv/bin/bbm status                      # League/team info
.venv/bin/bbm rankings [-p POS] [-t bat|pit] [--top N] [--refresh]
.venv/bin/bbm draft [--pick N]            # Interactive draft board
.venv/bin/bbm lineup [--date YYYY-MM-DD]  # Today's optimal lineup
.venv/bin/bbm waivers [-p POS]            # Pickup targets + drop candidates
.venv/bin/bbm report                      # Full daily report
.venv/bin/bbm scheduler install [--time HH:MM]
.venv/bin/bbm scheduler status
```

Projection cache lives in `.cache/`. Pass `--refresh` to any rankings/draft command to re-fetch from FanGraphs.

## Architecture

All source code is under `src/baseball_manager/`. The entry point is `cli.py`, which registers Click commands. All commands import lazily (inside the function body) to keep startup fast.

**Data flow for in-season commands** (`lineup`, `waivers`, `report`):
1. `YahooClient` fetches the live Yahoo roster (XML → dict via `xmltodict`)
2. `_load_ranked_roster()` in `cli.py` enriches Yahoo players with FanGraphs z-scores by matching on player name (lowercase)
3. Enriched roster is passed to optimizer or waiver engine

**Data flow for draft commands** (`rankings`, `draft`):
1. FanGraphs Steamer 2026 projections fetched/cached as JSON in `.cache/`
2. `draft/values.py` computes per-category z-scores, then normalizes batters and pitchers separately before merging into unified rankings
3. `draft/board.py` wraps rankings in a stateful `DraftBoard` that tracks picks and computes recommendations

## Key Design Decisions

**Yahoo API is read-only.** The Yahoo developer portal does not offer write scope (`fspt-w`) for new apps. All lineup and waiver recommendations are displayed for manual action on Yahoo. Playwright automation is a potential future addition.

**OAuth scope must include `openid`.** Using `fspt-r` alone returns a 401 "Invalid cookie" error from Yahoo. The working scope is `openid fspt-r`. Token is stored in `.yahoo_token.json` and auto-refreshes 5 minutes before expiry.

**Player positions are inferred from FanGraphs fields**, not a `Position` column (which doesn't exist in the API response):
- Batters: `minpos` field (e.g. `"SS"`, `"OF"`, `"DH"`)
- Pitchers: `GS >= 5` → SP, `SV >= 3` or `GS < 2` → RP

**Duplicate player rows** (split-season traded players) are deduplicated in `values.py` by keeping the row with the highest IP or PA.

**Z-score normalization** is done in two passes: once within each pool (batters, pitchers) to rank within the pool, then a second normalization across the combined pool for unified rankings. `ERA` and `WHIP` z-scores are inverted (lower is better).

## League & Season Constants

Hardcoded in `config.py` — update these each season:
- `GAME_ID = "469"` — Yahoo's 2026 MLB game ID (changes each year)
- `MY_TEAM_ID = "11"` — Cool Guys team ID in Blington league
- `LEAGUE_ID = "14637"` — from `.env` (has a typo key `leauge_id`, handled in config)

## Scheduler

The daily scheduler uses macOS launchd (not cron). The plist is installed to `~/Library/LaunchAgents/com.baseball-manager.daily.plist`. Logs go to `logs/` (gitignored). The scheduler runs `bbm report` via subprocess, saving each day's output to `logs/report_YYYY-MM-DD.log`.

## Playwright Automation

Browser automation for write operations (lineup changes, add/drop) lives in `src/baseball_manager/browser/`:

- `yahoo_browser.py` — `YahooBrowser` base class; cookie storage in `.playwright_cookies.json`
- `lineup_setter.py` — `LineupSetter`; edits Yahoo edit-roster page position selects
- `transactions.py` — `TransactionManager`; handles add/drop transactions

**One-time setup** (after `pip install -e .`):
```bash
playwright install chromium
bbm automate login   # opens headed browser; log in; press Enter to save session
```

**Commands:**
```bash
bbm automate login                      # Headed login + cookie save
bbm automate lineup [--date DATE]       # Apply optimal lineup on Yahoo
bbm automate lineup --dry-run           # Show moves without executing
bbm automate add "Player Name"          # Add free agent
bbm automate add "Player Name" --drop "Other Player"   # Add + drop
bbm automate drop "Player Name"         # Drop from roster
bbm automate waivers                    # Execute top pickup + worst drop
bbm automate waivers --dry-run          # Preview without executing
```

All `automate` commands (except `login`) run headless by default. Pass `--headed` to any command to show the browser window for debugging.

**Cookie file**: `.playwright_cookies.json` in project root (gitignored). If missing or expired, commands print "Run `bbm automate login` first."

**Screenshots on failure**: Saved to `logs/screenshots/` with timestamp + action name. Useful for diagnosing selector changes if Yahoo updates their markup.
