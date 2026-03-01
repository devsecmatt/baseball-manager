"""
Daily lineup optimizer for Cool Guys.

Strategy:
- Only start players who have a game today
- Fill every active slot with the highest-value eligible player
- Bench players with no game or lowest projected value
- Flag IL-eligible injured players
"""
from __future__ import annotations

from datetime import date
from tabulate import tabulate

from baseball_manager.config import ROSTER_SLOTS, LOWER_IS_BETTER, SCORING_CATEGORIES

# Slot fill priority order (fill scarce/specific slots first)
FILL_ORDER = ["C", "SS", "2B", "3B", "1B", "OF", "SP", "RP", "P", "Util", "BN", "IL"]

# Which positions are eligible for each slot
SLOT_ELIGIBLE: dict[str, list[str]] = {
    "C":    ["C"],
    "1B":   ["1B"],
    "2B":   ["2B"],
    "3B":   ["3B"],
    "SS":   ["SS"],
    "OF":   ["OF"],
    "Util": ["C", "1B", "2B", "3B", "SS", "OF", "DH", "Util"],
    "SP":   ["SP"],
    "RP":   ["RP"],
    "P":    ["SP", "RP"],
    "BN":   ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP", "DH", "Util"],
    "IL":   ["IL"],
}

ACTIVE_SLOTS = [s for s in ROSTER_SLOTS if s not in ("BN", "IL")]


def _player_value(player: dict) -> float:
    """Single-number value for sorting: use z_norm if available, else 0."""
    return player.get("z_norm", player.get("z_total", 0.0))


def _can_fill(player: dict, slot: str) -> bool:
    eligible = SLOT_ELIGIBLE.get(slot, [])
    return any(pos in eligible for pos in player.get("positions", []))


def _is_injured(player: dict) -> bool:
    status = str(player.get("status", "")).upper()
    return status in ("DL", "IL", "DTD", "O", "OUT", "10-DAY IL", "60-DAY IL")


def optimize_lineup(
    roster: list[dict],
    playing_teams: set[str],
    date_str: str | None = None,
) -> dict[str, list[dict]]:
    """
    Assign players to slots to maximize value with games today.

    Returns dict: slot -> [player, ...]
    """
    if date_str is None:
        date_str = date.today().isoformat()

    # Tag each player with whether they're playing today
    for p in roster:
        team = p.get("team", p.get("editorial_team_abbr", "")).upper()
        p["has_game"] = team in playing_teams
        p["_assigned"] = False

    # Sort by value descending
    pool = sorted(roster, key=_player_value, reverse=True)

    slots: dict[str, list[dict]] = {slot: [] for slot in ROSTER_SLOTS}

    def assign(player: dict, slot: str) -> None:
        slots[slot].append(player)
        player["_assigned"] = True
        player["_slot"] = slot

    # --- Pass 1: Fill active slots with players who have games ---
    for slot in FILL_ORDER:
        if slot in ("BN", "IL"):
            continue
        capacity = ROSTER_SLOTS.get(slot, 0)
        filled = 0
        for p in pool:
            if filled >= capacity:
                break
            if p["_assigned"]:
                continue
            if not p["has_game"]:
                continue
            if _is_injured(p):
                continue
            if _can_fill(p, slot):
                assign(p, slot)
                filled += 1

    # --- Pass 2: Fill remaining active slots with any player (no game) ---
    for slot in FILL_ORDER:
        if slot in ("BN", "IL"):
            continue
        capacity = ROSTER_SLOTS.get(slot, 0)
        currently_filled = len(slots[slot])
        for p in pool:
            if currently_filled >= capacity:
                break
            if p["_assigned"]:
                continue
            if _is_injured(p):
                continue
            if _can_fill(p, slot):
                assign(p, slot)
                currently_filled += 1

    # --- Pass 3: IL slot for injured players ---
    il_capacity = ROSTER_SLOTS.get("IL", 2)
    for p in pool:
        if len(slots["IL"]) >= il_capacity:
            break
        if not p["_assigned"] and _is_injured(p):
            assign(p, "IL")

    # --- Pass 4: Bench remaining ---
    bn_capacity = ROSTER_SLOTS.get("BN", 5)
    for p in pool:
        if len(slots["BN"]) >= bn_capacity:
            break
        if not p["_assigned"]:
            assign(p, "BN")

    return slots


def format_lineup(
    slots: dict[str, list[dict]],
    playing_teams: set[str],
) -> str:
    """Return a formatted string of the recommended lineup."""
    rows = []
    for slot in FILL_ORDER:
        players = slots.get(slot, [])
        capacity = ROSTER_SLOTS.get(slot, 0)
        for p in players:
            team = p.get("team", p.get("editorial_team_abbr", "?")).upper()
            has_game = "✓" if team in playing_teams else "-"
            z = round(p.get("z_norm", p.get("z_total", 0)), 2)
            proj = p.get("proj", {})
            if p.get("player_type") == "batter":
                stats = (f"R:{proj.get('R',0):.0f} HR:{proj.get('HR',0):.0f} "
                         f"RBI:{proj.get('RBI',0):.0f} SB:{proj.get('SB',0):.0f} "
                         f"AVG:{proj.get('AVG',0):.3f}")
            elif p.get("player_type") == "pitcher":
                stats = (f"W:{proj.get('W',0):.0f} SV:{proj.get('SV',0):.0f} "
                         f"K:{proj.get('K',0):.0f} ERA:{proj.get('ERA',0):.2f} "
                         f"WHIP:{proj.get('WHIP',0):.3f}")
            else:
                stats = ""
            rows.append([slot, has_game, p["name"], team, z, stats])
        # Show empty slots
        for _ in range(capacity - len(players)):
            rows.append([slot, "", "(empty)", "", "", ""])

    return tabulate(
        rows,
        headers=["Slot", "Game", "Player", "Team", "zVal", "Projections"],
    )


def lineup_changes(
    current_roster: list[dict],
    optimal_slots: dict[str, list[dict]],
) -> list[str]:
    """
    Compare current Yahoo roster positions to optimal and list recommended changes.
    current_roster: list of player dicts with 'selected_position' from Yahoo API.
    """
    changes = []
    for slot, players in optimal_slots.items():
        for p in players:
            current_pos = p.get("selected_position", {})
            if isinstance(current_pos, dict):
                current_pos = current_pos.get("position", "BN")
            if current_pos != slot:
                changes.append(
                    f"  Move {p['name']:25s} {current_pos} → {slot}"
                )
    return changes
