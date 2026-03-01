"""
MLB Stats API schedule fetcher (free, no auth required).
Used to determine which players are playing on a given date.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import requests

_CACHE_DIR = Path(__file__).parent.parent.parent.parent / ".cache"
_CACHE_DIR.mkdir(exist_ok=True)

_MLB_API = "https://statsapi.mlb.com/api/v1"


def _schedule_cache_path(d: date) -> Path:
    return _CACHE_DIR / f"schedule_{d.isoformat()}.json"


def get_games_on_date(d: date | None = None) -> list[dict]:
    """
    Return list of games on a given date.
    Each game dict has: game_pk, status, away_team, home_team, game_time.
    """
    if d is None:
        d = date.today()

    cache = _schedule_cache_path(d)
    # Only cache past dates (future dates can change)
    if cache.exists() and d < date.today():
        return json.loads(cache.read_text())

    resp = requests.get(
        f"{_MLB_API}/schedule",
        params={
            "sportId": 1,
            "date": d.isoformat(),
            "hydrate": "team",
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json()

    games = []
    for date_block in raw.get("dates", []):
        for g in date_block.get("games", []):
            games.append({
                "game_pk": g["gamePk"],
                "status": g["status"]["abstractGameState"],  # Preview/Live/Final
                "away_team": g["teams"]["away"]["team"]["abbreviation"],
                "home_team": g["teams"]["home"]["team"]["abbreviation"],
                "game_time": g.get("gameDate", ""),
            })

    if d < date.today():
        cache.write_text(json.dumps(games))
    return games


def get_playing_teams(d: date | None = None) -> set[str]:
    """Return set of MLB team abbreviations that have a game on this date."""
    games = get_games_on_date(d)
    teams = set()
    for g in games:
        teams.add(g["away_team"])
        teams.add(g["home_team"])
    return teams


def get_schedule_range(start: date, end: date) -> dict[str, set[str]]:
    """
    Return a dict mapping date strings to sets of playing team abbreviations.
    Useful for week-ahead planning.
    """
    result = {}
    current = start
    while current <= end:
        result[current.isoformat()] = get_playing_teams(current)
        current += timedelta(days=1)
    return result


def games_this_week(team_abbr: str, start: date | None = None) -> int:
    """Count how many games a team plays in the next 7 days."""
    if start is None:
        start = date.today()
    end = start + timedelta(days=6)
    schedule = get_schedule_range(start, end)
    return sum(1 for teams in schedule.values() if team_abbr.upper() in teams)
