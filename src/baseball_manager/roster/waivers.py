"""
Waiver wire and roster management recommendations.

Identifies:
- Top free agents worth picking up (by z-score value vs your roster)
- Players on your roster who are drop candidates
- Streaming pitcher targets (SPs with good upcoming matchups)
"""
from __future__ import annotations

from datetime import date, timedelta
from tabulate import tabulate

from baseball_manager.data.mlb_schedule import games_this_week


def _player_value(player: dict) -> float:
    return player.get("z_norm", player.get("z_total", 0.0))


def _is_injured(player: dict) -> bool:
    status = str(player.get("status", "")).upper()
    return status in ("DL", "IL", "DTD", "O", "OUT", "10-DAY IL", "60-DAY IL")


def find_pickup_targets(
    my_roster: list[dict],
    free_agents: list[dict],
    top_n: int = 15,
    position: str | None = None,
) -> list[dict]:
    """
    Return top free agent pickup targets ranked by z-value.
    Filters out players below the weakest player on your roster.
    """
    if not my_roster:
        roster_floor = -99.0
    else:
        roster_floor = min(_player_value(p) for p in my_roster)

    candidates = [
        p for p in free_agents
        if _player_value(p) > roster_floor
        and not _is_injured(p)
        and (position is None or position.upper() in p.get("positions", []))
    ]
    candidates.sort(key=_player_value, reverse=True)
    return candidates[:top_n]


def find_drop_candidates(my_roster: list[dict], top_n: int = 5) -> list[dict]:
    """
    Return roster players who are the weakest holds.
    Prioritizes: injured, low z-value, no games this week.
    """
    scored = []
    today = date.today()
    for p in my_roster:
        val = _player_value(p)
        injured_penalty = -2.0 if _is_injured(p) else 0.0
        team = p.get("team", "").upper()
        weekly_games = games_this_week(team, start=today)
        schedule_penalty = -0.5 * max(0, 4 - weekly_games)  # penalize <4 games/week
        drop_score = val + injured_penalty + schedule_penalty
        scored.append((drop_score, p))

    scored.sort(key=lambda x: x[0])
    return [p for _, p in scored[:top_n]]


def find_streaming_sps(
    free_agents: list[dict],
    playing_teams: set[str],
    top_n: int = 10,
) -> list[dict]:
    """
    Identify streaming SP targets: SPs with a game today and good projections.
    """
    streamers = [
        p for p in free_agents
        if "SP" in p.get("positions", [])
        and p.get("team", "").upper() in playing_teams
        and not _is_injured(p)
    ]
    streamers.sort(key=_player_value, reverse=True)
    return streamers[:top_n]


def format_pickups(targets: list[dict]) -> str:
    rows = []
    for p in targets:
        proj = p.get("proj", {})
        if p.get("player_type") == "batter":
            stats = (f"R:{proj.get('R',0):.0f} HR:{proj.get('HR',0):.0f} "
                     f"RBI:{proj.get('RBI',0):.0f} SB:{proj.get('SB',0):.0f} "
                     f"AVG:{proj.get('AVG',0):.3f} OPS:{proj.get('OPS',0):.3f}")
        else:
            stats = (f"W:{proj.get('W',0):.0f} SV:{proj.get('SV',0):.0f} "
                     f"K:{proj.get('K',0):.0f} ERA:{proj.get('ERA',0):.2f} "
                     f"WHIP:{proj.get('WHIP',0):.3f}")
        rows.append([
            p["name"],
            p.get("team", "?"),
            "/".join(p.get("positions", [])),
            round(_player_value(p), 2),
            stats,
        ])
    return tabulate(rows, headers=["Player", "Team", "Pos", "zVal", "Projections"])


def format_drops(candidates: list[dict]) -> str:
    rows = []
    for p in candidates:
        status = "IL" if _is_injured(p) else "OK"
        team = p.get("team", "?").upper()
        weekly = games_this_week(team)
        rows.append([
            p["name"],
            team,
            "/".join(p.get("positions", [])),
            round(_player_value(p), 2),
            f"{weekly}g/wk",
            status,
        ])
    return tabulate(rows, headers=["Player", "Team", "Pos", "zVal", "Schedule", "Status"])
