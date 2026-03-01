"""Yahoo Fantasy Sports API v2 client."""
from __future__ import annotations

import xmltodict
import requests

from baseball_manager.auth.yahoo_oauth import get_access_token
from baseball_manager.config import LEAGUE_ID, YAHOO_API_BASE


class YahooClient:
    """Thin wrapper around Yahoo Fantasy Sports API v2.

    Handles authentication headers, XML parsing, and league key resolution.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._game_id: str | None = None
        self._league_key: str | None = None
        self._team_key: str | None = None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {get_access_token()}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{YAHOO_API_BASE}/{path}"
        resp = self._session.get(url, headers=self._headers(), params=params or {})
        resp.raise_for_status()
        return xmltodict.parse(resp.text)["fantasy_content"]

    # ------------------------------------------------------------------
    # Game / League identity
    # ------------------------------------------------------------------

    def get_game_id(self) -> str:
        """Resolve current MLB season game_id from Yahoo."""
        if self._game_id:
            return self._game_id
        data = self._get("games;game_codes=mlb;seasons=2026")
        games = data["games"]["game"]
        # May return a list or single dict
        if isinstance(games, list):
            game = games[0]
        else:
            game = games
        self._game_id = game["game_id"]
        return self._game_id

    def get_league_key(self) -> str:
        if self._league_key:
            return self._league_key
        game_id = self.get_game_id()
        self._league_key = f"{game_id}.l.{LEAGUE_ID}"
        return self._league_key

    def get_league_info(self) -> dict:
        lk = self.get_league_key()
        return self._get(f"league/{lk}")["league"]

    def get_my_team_key(self) -> str:
        """Find our team key within the league."""
        if self._team_key:
            return self._team_key
        lk = self.get_league_key()
        data = self._get(f"league/{lk}/teams")
        teams = data["league"]["teams"]["team"]
        if not isinstance(teams, list):
            teams = [teams]
        # Our team is the one flagged is_owned_by_current_login
        for team in teams:
            if team.get("is_owned_by_current_login") == "1":
                self._team_key = team["team_key"]
                return self._team_key
        raise RuntimeError("Could not find your team in the league.")

    # ------------------------------------------------------------------
    # Teams & standings
    # ------------------------------------------------------------------

    def get_teams(self) -> list[dict]:
        lk = self.get_league_key()
        data = self._get(f"league/{lk}/teams")
        teams = data["league"]["teams"]["team"]
        return teams if isinstance(teams, list) else [teams]

    def get_standings(self) -> list[dict]:
        lk = self.get_league_key()
        data = self._get(f"league/{lk}/standings")
        teams = data["league"]["standings"]["teams"]["team"]
        return teams if isinstance(teams, list) else [teams]

    # ------------------------------------------------------------------
    # Roster
    # ------------------------------------------------------------------

    def get_roster(self, team_key: str | None = None, date: str | None = None) -> list[dict]:
        """Get roster for a team. Returns list of player dicts."""
        tk = team_key or self.get_my_team_key()
        path = f"team/{tk}/roster"
        if date:
            path += f";date={date}"
        data = self._get(path)
        players = data["team"]["roster"]["players"]["player"]
        return players if isinstance(players, list) else [players]

    def get_my_roster(self, date: str | None = None) -> list[dict]:
        return self.get_roster(team_key=self.get_my_team_key(), date=date)

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------

    def get_player(self, player_key: str) -> dict:
        lk = self.get_league_key()
        data = self._get(f"league/{lk}/players;player_keys={player_key}/stats")
        return data["league"]["players"]["player"]

    def search_players(
        self,
        status: str = "A",  # A=available, FA=free agent, W=waivers, T=taken
        position: str | None = None,
        start: int = 0,
        count: int = 25,
    ) -> list[dict]:
        """Search available players in the league."""
        lk = self.get_league_key()
        filters = f";status={status};start={start};count={count}"
        if position:
            filters += f";position={position}"
        data = self._get(f"league/{lk}/players{filters}/stats")
        players = data["league"].get("players", {}).get("player", [])
        return players if isinstance(players, list) else [players]

    def get_free_agents(self, position: str | None = None, count: int = 25) -> list[dict]:
        return self.search_players(status="FA", position=position, count=count)

    # ------------------------------------------------------------------
    # Matchups
    # ------------------------------------------------------------------

    def get_scoreboard(self, week: int | None = None) -> dict:
        lk = self.get_league_key()
        path = f"league/{lk}/scoreboard"
        if week:
            path += f";week={week}"
        return self._get(path)["league"]

    def get_my_matchup(self, week: int | None = None) -> dict | None:
        board = self.get_scoreboard(week=week)
        matchups = board.get("scoreboard", {}).get("matchups", {}).get("matchup", [])
        if not isinstance(matchups, list):
            matchups = [matchups]
        my_team_key = self.get_my_team_key()
        for matchup in matchups:
            teams = matchup.get("teams", {}).get("team", [])
            if not isinstance(teams, list):
                teams = [teams]
            for team in teams:
                if team.get("team_key") == my_team_key:
                    return matchup
        return None

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Draft
    # ------------------------------------------------------------------

    def get_draft_results(self) -> list[dict]:
        lk = self.get_league_key()
        data = self._get(f"league/{lk}/draftresults")
        picks = data["league"]["draft_picks"]["draft_pick"]
        return picks if isinstance(picks, list) else [picks]

    def get_draft_status(self) -> dict:
        return self.get_league_info()
