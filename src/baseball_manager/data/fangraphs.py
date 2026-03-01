"""Fetch FanGraphs Steamer 2026 projections."""
from __future__ import annotations

import json
from pathlib import Path

import requests

_CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)

_BAT_CACHE = _CACHE_DIR / "steamer_bat_2026.json"
_PIT_CACHE = _CACHE_DIR / "steamer_pit_2026.json"

_FG_API = "https://www.fangraphs.com/api/projections"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.fangraphs.com/projections.aspx",
}


def _fetch(stats: str) -> list[dict]:
    params = {
        "type": "steamer",
        "stats": stats,
        "pos": "all",
        "team": "0",
        "players": "0",
        "lg": "all",
    }
    resp = requests.get(_FG_API, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_batting_projections(force_refresh: bool = False) -> list[dict]:
    """Return Steamer 2026 batting projections (cached)."""
    if _BAT_CACHE.exists() and not force_refresh:
        return json.loads(_BAT_CACHE.read_text())
    print("Fetching FanGraphs Steamer 2026 batting projections...")
    data = _fetch("bat")
    _BAT_CACHE.write_text(json.dumps(data))
    print(f"  Cached {len(data)} batters.")
    return data


def get_pitching_projections(force_refresh: bool = False) -> list[dict]:
    """Return Steamer 2026 pitching projections (cached)."""
    if _PIT_CACHE.exists() and not force_refresh:
        return json.loads(_PIT_CACHE.read_text())
    print("Fetching FanGraphs Steamer 2026 pitching projections...")
    data = _fetch("pit")
    _PIT_CACHE.write_text(json.dumps(data))
    print(f"  Cached {len(data)} pitchers.")
    return data
