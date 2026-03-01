"""
Z-score fantasy value calculator tuned to Blington league scoring.

Scoring categories:
  Batting:  R, HR, RBI, SB, AVG, OPS
  Pitching: W, SV, K, ERA, WHIP

Method: z-scores above replacement level, summed across all relevant categories.
ERA and WHIP are inverted (lower is better).
"""
from __future__ import annotations

import statistics
from typing import Any

# FanGraphs field name -> our category name
BAT_FIELD_MAP = {
    "R": "R",
    "HR": "HR",
    "RBI": "RBI",
    "SB": "SB",
    "AVG": "AVG",
    "OPS": "OPS",
}

PIT_FIELD_MAP = {
    "W": "W",
    "SV": "SV",
    "SO": "K",   # FanGraphs uses SO for strikeouts
    "ERA": "ERA",
    "WHIP": "WHIP",
}

# Lower is better for these — z-score gets inverted
LOWER_IS_BETTER = {"ERA", "WHIP"}

# Minimum PA/IP to include in replacement level calculation
MIN_PA = 100
MIN_IP = 20

# How many players are "rostered" in a 12-team league at each position
# Used to set replacement level (z-score baseline)
ROSTER_SIZE = 12
PLAYERS_PER_TEAM = 25
TOTAL_ROSTERED = ROSTER_SIZE * PLAYERS_PER_TEAM  # ~300 total

# Approximate positional counts drafted across 12 teams
POSITION_COUNTS = {
    "C": 12 * 1,
    "1B": 12 * 2,   # 1B + some Util
    "2B": 12 * 2,
    "3B": 12 * 2,
    "SS": 12 * 2,
    "OF": 12 * 4,
    "SP": 12 * 4,
    "RP": 12 * 4,
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _batter_positions(player: dict) -> list[str]:
    """Parse FanGraphs batter position using 'minpos' field."""
    minpos = str(player.get("minpos", "Util")).strip().upper()
    # Map DH to Util for Yahoo eligibility
    if minpos == "DH":
        return ["DH", "Util"]
    if minpos in ("C", "1B", "2B", "3B", "SS", "OF"):
        return [minpos]
    return ["Util"]


def _pitcher_positions(player: dict) -> list[str]:
    """Determine SP vs RP from GS and SV projections."""
    gs = _safe_float(player.get("GS", 0))
    sv = _safe_float(player.get("SV", 0))
    g = _safe_float(player.get("G", 1))
    if gs >= 5:
        return ["SP"]
    if sv >= 3 or (gs < 2 and g > 10):
        return ["RP"]
    # Two-way or tweener: list both
    return ["SP", "RP"]


def _deduplicate(players: list[dict], key: str = "PlayerName") -> list[dict]:
    """Keep the row with highest IP/PA when a player appears multiple times (trades/splits)."""
    seen: dict[str, dict] = {}
    volume_key = "IP" if "IP" in (players[0] if players else {}) else "PA"
    for p in players:
        name = p.get(key, "")
        if not name:
            continue
        vol = _safe_float(p.get(volume_key, 0))
        if name not in seen or vol > _safe_float(seen[name].get(volume_key, 0)):
            seen[name] = p
    return list(seen.values())


def calculate_batter_values(batters: list[dict]) -> list[dict]:
    """
    Return batters enriched with z-score fantasy values.
    Filters to players with >= MIN_PA projected PA.
    """
    batters = _deduplicate(batters)
    eligible = [
        p for p in batters
        if _safe_float(p.get("PA", p.get("AB", 0))) >= MIN_PA
    ]

    # Build per-category lists for mean/stdev
    cat_values: dict[str, list[float]] = {cat: [] for cat in BAT_FIELD_MAP}
    for p in eligible:
        for fg_field, cat in BAT_FIELD_MAP.items():
            cat_values[cat].append(_safe_float(p.get(fg_field, 0)))

    # Compute mean and stdev per category
    stats: dict[str, tuple[float, float]] = {}
    for cat, vals in cat_values.items():
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 1.0
        stats[cat] = (mean, stdev)

    results = []
    for p in eligible:
        z_total = 0.0
        cat_z: dict[str, float] = {}
        for fg_field, cat in BAT_FIELD_MAP.items():
            val = _safe_float(p.get(fg_field, 0))
            mean, stdev = stats[cat]
            z = (val - mean) / stdev if stdev > 0 else 0.0
            if cat in LOWER_IS_BETTER:
                z = -z
            cat_z[cat] = round(z, 3)
            z_total += z

        positions = _batter_positions(p)
        results.append({
            "name": p.get("PlayerName", p.get("Name", "Unknown")),
            "team": p.get("Team", "?"),
            "positions": positions,
            "player_type": "batter",
            "pa": int(_safe_float(p.get("PA", p.get("AB", 0)))),
            "proj": {cat: round(_safe_float(p.get(fg, 0)), 3) for fg, cat in BAT_FIELD_MAP.items()},
            "z_scores": cat_z,
            "z_total": round(z_total, 3),
            "fangraphs_id": str(p.get("playerid", p.get("xMLBAMID", ""))),
        })

    results.sort(key=lambda x: x["z_total"], reverse=True)
    for i, p in enumerate(results):
        p["rank_bat"] = i + 1
    return results


def calculate_pitcher_values(pitchers: list[dict]) -> list[dict]:
    """
    Return pitchers enriched with z-score fantasy values.
    Filters to players with >= MIN_IP projected IP.
    """
    pitchers = _deduplicate(pitchers)
    eligible = [
        p for p in pitchers
        if _safe_float(p.get("IP", 0)) >= MIN_IP
    ]

    cat_values: dict[str, list[float]] = {cat: [] for cat in PIT_FIELD_MAP.values()}
    for p in eligible:
        for fg_field, cat in PIT_FIELD_MAP.items():
            cat_values[cat].append(_safe_float(p.get(fg_field, 0)))

    stats: dict[str, tuple[float, float]] = {}
    for cat, vals in cat_values.items():
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 1.0
        stats[cat] = (mean, stdev)

    results = []
    for p in eligible:
        z_total = 0.0
        cat_z: dict[str, float] = {}
        for fg_field, cat in PIT_FIELD_MAP.items():
            val = _safe_float(p.get(fg_field, 0))
            mean, stdev = stats[cat]
            z = (val - mean) / stdev if stdev > 0 else 0.0
            if cat in LOWER_IS_BETTER:
                z = -z
            cat_z[cat] = round(z, 3)
            z_total += z

        positions = _pitcher_positions(p)

        results.append({
            "name": p.get("PlayerName", p.get("Name", "Unknown")),
            "team": p.get("Team", "?"),
            "positions": positions,
            "player_type": "pitcher",
            "ip": round(_safe_float(p.get("IP", 0)), 1),
            "proj": {cat: round(_safe_float(p.get(fg, 0)), 3) for fg, cat in PIT_FIELD_MAP.items()},
            "z_scores": cat_z,
            "z_total": round(z_total, 3),
            "fangraphs_id": str(p.get("playerid", p.get("xMLBAMID", ""))),
        })

    results.sort(key=lambda x: x["z_total"], reverse=True)
    for i, p in enumerate(results):
        p["rank_pit"] = i + 1
    return results


def build_unified_rankings(batters: list[dict], pitchers: list[dict]) -> list[dict]:
    """
    Merge batters and pitchers into a single overall ranking.

    Z-scores are on different scales for hitters vs pitchers, so we
    normalize each pool separately before merging.
    """
    def _normalize(players: list[dict]) -> list[dict]:
        scores = [p["z_total"] for p in players]
        mean = statistics.mean(scores)
        stdev = statistics.stdev(scores) if len(scores) > 1 else 1.0
        for p in players:
            p["z_norm"] = (p["z_total"] - mean) / stdev
        return players

    batters = _normalize(batters)
    pitchers = _normalize(pitchers)

    all_players = batters + pitchers
    all_players.sort(key=lambda x: x["z_norm"], reverse=True)
    for i, p in enumerate(all_players):
        p["overall_rank"] = i + 1

    return all_players
