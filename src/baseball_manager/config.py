"""Central configuration loaded from .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env")

# Yahoo API credentials
CLIENT_ID = os.environ["client_id"]
CLIENT_SECRET = os.environ["client_secret"]
# Handle typo in .env: "leauge_id" vs "league_id"
LEAGUE_ID = os.environ.get("league_id") or os.environ.get("leauge_id")
if not LEAGUE_ID:
    raise EnvironmentError("league_id (or leauge_id) not found in .env")

# Yahoo OAuth endpoints
YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# 2026 season constants (resolved from API)
GAME_ID = "469"
LEAGUE_KEY = f"{GAME_ID}.l.{LEAGUE_ID}"
MY_TEAM_ID = "11"
MY_TEAM_KEY = f"{LEAGUE_KEY}.t.{MY_TEAM_ID}"
MY_TEAM_NAME = "Cool Guys"

# Token storage
TOKEN_FILE = _ROOT / ".yahoo_token.json"

# League configuration (from league docs)
SCORING_CATEGORIES = {
    "batting": ["R", "HR", "RBI", "SB", "AVG", "OPS"],
    "pitching": ["W", "SV", "K", "ERA", "WHIP"],
}

ROSTER_SLOTS = {
    "C": 1,
    "1B": 1,
    "2B": 1,
    "3B": 1,
    "SS": 1,
    "OF": 3,
    "Util": 2,
    "SP": 2,
    "RP": 2,
    "P": 4,
    "BN": 5,
    "IL": 2,
}

ACTIVE_SLOTS = ["C", "1B", "2B", "3B", "SS", "OF", "Util", "SP", "RP", "P"]
BENCH_SLOTS = ["BN", "IL"]
TOTAL_ACTIVE = sum(v for k, v in ROSTER_SLOTS.items() if k not in BENCH_SLOTS)

# Lower is better for these pitching stats
LOWER_IS_BETTER = {"ERA", "WHIP"}

# Stat name mappings (Yahoo API name -> our short name)
STAT_ID_MAP = {
    # Batting
    "7": "R",
    "12": "HR",
    "13": "RBI",
    "16": "SB",
    "3": "AVG",
    "55": "OPS",
    # Pitching
    "28": "W",
    "32": "SV",
    "42": "K",
    "26": "ERA",
    "27": "WHIP",
}
