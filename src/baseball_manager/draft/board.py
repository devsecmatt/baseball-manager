"""
Interactive draft board for Blington snake draft.

Usage:
    board = DraftBoard(rankings, num_teams=12, my_pick=11, num_rounds=25)
    board.run()
"""
from __future__ import annotations

from tabulate import tabulate

from baseball_manager.config import (
    SCORING_CATEGORIES,
    ROSTER_SLOTS,
)

POSITION_DISPLAY_ORDER = ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP", "Util", "BN"]

# Which positions fill which roster slots
SLOT_ELIGIBLE: dict[str, list[str]] = {
    "C": ["C"],
    "1B": ["1B"],
    "2B": ["2B"],
    "3B": ["3B"],
    "SS": ["SS"],
    "OF": ["OF"],
    "Util": ["C", "1B", "2B", "3B", "SS", "OF", "DH"],
    "SP": ["SP"],
    "RP": ["RP"],
    "P": ["SP", "RP"],
    "BN": ["C", "1B", "2B", "3B", "SS", "OF", "SP", "RP", "DH", "Util"],
}


class DraftBoard:
    def __init__(
        self,
        rankings: list[dict],
        num_teams: int = 12,
        my_pick: int = 11,     # 1-indexed draft position
        num_rounds: int = 25,
    ):
        self.rankings = rankings
        self.num_teams = num_teams
        self.my_pick = my_pick
        self.num_rounds = num_rounds

        self.drafted: dict[str, dict] = {}       # name -> player dict
        self.my_roster: list[dict] = []
        self.current_pick = 1                    # overall pick number

    # ------------------------------------------------------------------
    # Snake draft pick calculations
    # ------------------------------------------------------------------

    def _pick_number_for(self, round_num: int, team_pick: int) -> int:
        """Overall pick number for a given round and team slot."""
        if round_num % 2 == 1:  # odd round: normal order
            return (round_num - 1) * self.num_teams + team_pick
        else:                    # even round: reversed
            return (round_num - 1) * self.num_teams + (self.num_teams - team_pick + 1)

    def my_picks(self) -> list[int]:
        picks = []
        for r in range(1, self.num_rounds + 1):
            picks.append(self._pick_number_for(r, self.my_pick))
        return sorted(picks)

    def current_round(self) -> int:
        return (self.current_pick - 1) // self.num_teams + 1

    def is_my_pick(self) -> bool:
        return self.current_pick in self.my_picks()

    def next_my_pick(self) -> int | None:
        future = [p for p in self.my_picks() if p >= self.current_pick]
        return future[0] if future else None

    def picks_until_mine(self) -> int:
        nxt = self.next_my_pick()
        return (nxt - self.current_pick) if nxt else 0

    # ------------------------------------------------------------------
    # Available players
    # ------------------------------------------------------------------

    def available(self) -> list[dict]:
        return [p for p in self.rankings if p["name"] not in self.drafted]

    def available_at(self, position: str) -> list[dict]:
        return [
            p for p in self.available()
            if position in p["positions"]
        ]

    def top_available(self, n: int = 10) -> list[dict]:
        return self.available()[:n]

    # ------------------------------------------------------------------
    # Roster analysis
    # ------------------------------------------------------------------

    def _roster_slot_filled(self, slot: str) -> int:
        """Count how many of my roster players can fill this slot."""
        eligible_positions = SLOT_ELIGIBLE.get(slot, [])
        count = 0
        for p in self.my_roster:
            if any(pos in eligible_positions for pos in p["positions"]):
                count += 1
        return count

    def roster_needs(self) -> dict[str, int]:
        """Return remaining open slots by position."""
        needs = {}
        for slot, total in ROSTER_SLOTS.items():
            if slot == "IL":
                continue
            filled = self._roster_slot_filled(slot)
            remaining = max(0, total - filled)
            if remaining > 0:
                needs[slot] = remaining
        return needs

    def category_totals(self) -> dict[str, float]:
        """Sum projected stats across my roster."""
        totals: dict[str, float] = {}
        all_cats = SCORING_CATEGORIES["batting"] + SCORING_CATEGORIES["pitching"]
        for cat in all_cats:
            totals[cat] = 0.0
        for p in self.my_roster:
            for cat, val in p.get("proj", {}).items():
                if cat in totals:
                    totals[cat] += val
        return totals

    def recommend(self, top_n: int = 5) -> list[dict]:
        """
        Recommend best available players weighted by:
        1. Overall z-score value
        2. Bonus for filling a positional need
        3. Positional scarcity (C, SS, 2B score higher when scarce)
        """
        needs = self.roster_needs()
        scarcity_bonus = {"C": 0.5, "SS": 0.3, "2B": 0.2}
        avail = self.available()

        scored = []
        for p in avail:
            score = p["z_norm"]
            # Positional need bonus
            for pos in p["positions"]:
                if pos in needs:
                    score += 0.3
                    break
            # Scarcity bonus
            for pos in p["positions"]:
                if pos in scarcity_bonus:
                    score += scarcity_bonus[pos]
                    break
            scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_n]]

    # ------------------------------------------------------------------
    # Draft actions
    # ------------------------------------------------------------------

    def mark_drafted(self, name: str, by_me: bool = False) -> dict | None:
        """Mark a player as drafted. Returns the player dict if found."""
        matches = [p for p in self.rankings if p["name"].lower() == name.lower()]
        if not matches:
            # Fuzzy: try partial match
            matches = [p for p in self.rankings if name.lower() in p["name"].lower()]
        if not matches:
            return None
        player = matches[0]
        self.drafted[player["name"]] = player
        if by_me:
            self.my_roster.append(player)
        self.current_pick += 1
        return player

    def undo_last(self) -> None:
        """Undo the last pick."""
        if self.current_pick <= 1:
            return
        self.current_pick -= 1
        if self.drafted:
            last_name = list(self.drafted.keys())[-1]
            player = self.drafted.pop(last_name)
            if player in self.my_roster:
                self.my_roster.remove(player)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _fmt_positions(self, p: dict) -> str:
        return "/".join(p["positions"])

    def _fmt_proj(self, p: dict) -> str:
        proj = p.get("proj", {})
        if p["player_type"] == "batter":
            return (
                f"R:{proj.get('R',0):.0f} HR:{proj.get('HR',0):.0f} "
                f"RBI:{proj.get('RBI',0):.0f} SB:{proj.get('SB',0):.0f} "
                f"AVG:{proj.get('AVG',0):.3f} OPS:{proj.get('OPS',0):.3f}"
            )
        else:
            return (
                f"W:{proj.get('W',0):.0f} SV:{proj.get('SV',0):.0f} "
                f"K:{proj.get('K',0):.0f} ERA:{proj.get('ERA',0):.2f} "
                f"WHIP:{proj.get('WHIP',0):.3f}"
            )

    def show_top_available(self, n: int = 20, position: str | None = None) -> None:
        players = self.available_at(position) if position else self.available()
        players = players[:n]
        rows = []
        for p in players:
            rows.append([
                p["overall_rank"],
                p["name"],
                p["team"],
                self._fmt_positions(p),
                round(p["z_norm"], 2),
                self._fmt_proj(p),
            ])
        print(tabulate(rows, headers=["Rank", "Name", "Team", "Pos", "zVal", "Projections"]))

    def show_recommendations(self) -> None:
        recs = self.recommend(top_n=8)
        print(f"\n{'='*70}")
        print(f"  PICK {self.current_pick}  |  Round {self.current_round()}  |  "
              f"{'*** YOUR PICK ***' if self.is_my_pick() else f'{self.picks_until_mine()} picks until yours'}")
        print(f"{'='*70}")
        needs = self.roster_needs()
        print(f"  Roster needs: {', '.join(f'{k}({v})' for k,v in needs.items()) or 'Full!'}")
        print(f"\n  TOP RECOMMENDATIONS:")
        rows = []
        for i, p in enumerate(recs, 1):
            rows.append([
                i,
                p["name"],
                p["team"],
                self._fmt_positions(p),
                round(p["z_norm"], 2),
                self._fmt_proj(p),
            ])
        print(tabulate(rows, headers=["#", "Name", "Team", "Pos", "zVal", "Projections"]))

    def show_my_roster(self) -> None:
        if not self.my_roster:
            print("  (no players drafted yet)")
            return
        rows = []
        for p in self.my_roster:
            rows.append([
                self._fmt_positions(p),
                p["name"],
                p["team"],
                round(p["z_norm"], 2),
                self._fmt_proj(p),
            ])
        print(tabulate(rows, headers=["Pos", "Name", "Team", "zVal", "Projections"]))

    def show_category_balance(self) -> None:
        totals = self.category_totals()
        print("\n  Projected Category Totals (your roster so far):")
        bat_row = [(cat, f"{totals.get(cat, 0):.1f}") for cat in SCORING_CATEGORIES["batting"]]
        pit_row = [(cat, f"{totals.get(cat, 0):.2f}") for cat in SCORING_CATEGORIES["pitching"]]
        print("  Batting:  " + "  ".join(f"{c}: {v}" for c, v in bat_row))
        print("  Pitching: " + "  ".join(f"{c}: {v}" for c, v in pit_row))

    # ------------------------------------------------------------------
    # Interactive CLI loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        print("\n" + "="*70)
        print("  BLINGTON DRAFT ASSISTANT — Cool Guys (Pick #11)")
        print("  Snake draft | 25 rounds | 12 teams")
        print("  Commands: [enter]=next pick  r=recs  t=top20  p <pos>=by position")
        print("            m=my roster  c=category balance  u=undo  q=quit")
        print("="*70)

        while self.current_pick <= self.num_teams * self.num_rounds:
            self.show_recommendations()

            try:
                raw = input("\n  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nDraft paused.")
                break

            if raw == "q":
                print("Draft session ended.")
                break
            elif raw == "r":
                self.show_recommendations()
            elif raw == "t":
                print("\n  Top 20 Available:")
                self.show_top_available(20)
            elif raw.startswith("p "):
                pos = raw[2:].upper()
                print(f"\n  Top Available at {pos}:")
                self.show_top_available(15, position=pos)
            elif raw == "m":
                print("\n  Your Roster:")
                self.show_my_roster()
            elif raw == "c":
                self.show_category_balance()
            elif raw == "u":
                self.undo_last()
                print(f"  Undone. Back to pick {self.current_pick}.")
            elif raw == "":
                # Advance pick without drafting anyone (someone else picked, unknown player)
                self.current_pick += 1
            else:
                # Treat input as a player name being drafted
                # If it starts with "me:" it's our pick
                by_me = raw.startswith("me:")
                name = raw[3:].strip() if by_me else raw

                if self.is_my_pick() and not by_me:
                    by_me = True  # If it's our pick turn, assume it's us

                player = self.mark_drafted(name, by_me=by_me)
                if player:
                    owner = "YOU" if by_me else "opponent"
                    print(f"  ✓ [{owner}] {player['name']} ({self._fmt_positions(player)}) drafted — pick {self.current_pick - 1}")
                    if by_me:
                        self.show_category_balance()
                else:
                    print(f"  Player '{name}' not found. Try a partial name.")
                    self.current_pick -= 1  # revert the increment from mark_drafted attempt
