# baseball-manager

AI-powered Yahoo Fantasy Baseball manager for the **Blington** league (Cool Guys, pick #11).
12-team H2H, daily lineups, snake draft, 25 rounds.

---

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Create a `.env` file in the project root:
```
client_id=YOUR_YAHOO_CLIENT_ID
client_secret=YOUR_YAHOO_CLIENT_SECRET
league_id=14637
```

Authorize with Yahoo (one-time):
```bash
.venv/bin/bbm auth
```
A browser will open. Approve access, then copy the full redirect URL
(`https://localhost/?code=...`) from your browser's address bar and paste it at the prompt.

---

## Commands

### `bbm auth`
Authorize with Yahoo OAuth2. Run once; token auto-refreshes thereafter.

### `bbm status`
Show league info, your team, and current roster.

### `bbm roster`
Show your current roster with positions and MLB team.

### `bbm matchup`
Show current week's head-to-head matchup stats.

### `bbm rankings`
Show pre-draft player rankings based on FanGraphs Steamer 2026 projections
and z-score valuation across all 11 scoring categories.

```bash
bbm rankings                  # Top 50 overall
bbm rankings --top 100        # Top 100 overall
bbm rankings -p C             # Catchers only
bbm rankings -p SS            # Shortstops only
bbm rankings -p OF            # Outfielders only
bbm rankings -p SP            # Starting pitchers only
bbm rankings -p RP            # Relief pitchers only
bbm rankings -t bat           # All batters
bbm rankings -t pit           # All pitchers
bbm rankings --refresh        # Re-fetch latest projections from FanGraphs
```

Rankings use z-scores normalized across the 6 batting categories
(R, HR, RBI, SB, AVG, OPS) and 5 pitching categories (W, SV, K, ERA, WHIP).
ERA and WHIP are inverted so lower = better.

---

### `bbm draft` — Interactive Draft Assistant

Launch the real-time draft board. Use this on draft day.

```bash
bbm draft                     # Default: pick slot #11
bbm draft --pick 11           # Explicit pick slot (1–12)
bbm draft --refresh           # Re-fetch projections before starting
```

#### Draft Board Commands

| Command | Action |
|---|---|
| `[player name]` | Mark player as drafted by an opponent |
| `me: [player name]` | Mark player as YOUR pick (auto-assumed on your turn) |
| `r` | Show recommendations for current pick |
| `t` | Show top 20 available players overall |
| `p [POS]` | Show top available at a position (e.g. `p SS`, `p C`, `p SP`) |
| `m` | Show your current roster |
| `c` | Show projected category totals for your roster so far |
| `u` | Undo the last pick |
| `[enter]` | Advance to next pick without recording a player (unknown opponent pick) |
| `q` | Quit and save session |

#### Example Draft Session

```
> t                          # See top 20 available before your pick
> Bobby Witt Jr.             # Opponent drafted Witt (pick 1)
> Aaron Judge                # Opponent drafted Judge (pick 2)
...
> [enter]                    # Skip past picks you don't know
> Tarik Skubal               # Your turn — auto-marked as YOUR pick
> m                          # Review your roster
> c                          # Check category balance
> p C                        # Check top catchers before next pick
> Cal Raleigh                # Your next pick
> u                          # Undo if you change your mind
```

#### How Recommendations Work

On each pick the board shows:
- Your current roster needs by position
- Top 8 recommended players weighted by overall z-score value,
  positional need bonus, and scarcity bonus (C, SS, 2B)
- Projected stats for each recommendation

#### Snake Draft Pick Schedule (Pick #11, 12 teams)

| Round | Your Pick # |
|---|---|
| 1 | 11 |
| 2 | 14 (back-to-back with round 1) |
| 3 | 35 |
| 4 | 38 |
| ... | ... |

You get picks **11 & 14** in rounds 1–2 — a strong back-to-back position.

---

### `bbm lineup`
Show today's recommended lineup with players to start/bench based on
game schedule, matchup, and projected output.

```bash
bbm lineup                    # Today's lineup
bbm lineup --date 2026-04-15  # Lineup for a specific date
```

### `bbm waivers`
Show top waiver wire pickups and drop candidates for your current roster.

```bash
bbm waivers                   # Top 15 pickups + 5 drop candidates
bbm waivers -p SP             # Pitchers only
bbm waivers -n 25             # Show top 25 pickups
```

### `bbm report`
Full daily report combining matchup status, lineup recommendation, and top waiver targets.

```bash
bbm report
```

---

### `bbm scheduler` — Automated Daily Reports

Installs a macOS launchd agent that runs `bbm report` automatically each morning.

```bash
# Install — runs at 8:00 AM daily
bbm scheduler install

# Install at a custom time
bbm scheduler install --time 07:30

# Check status and view recent output
bbm scheduler status

# Run the report immediately (one-shot, no daemon)
bbm scheduler now

# Run daemon in foreground (for testing)
bbm scheduler run

# Remove the scheduler
bbm scheduler uninstall
```

The scheduler writes logs to `logs/`:
- `logs/scheduler.log` — daemon activity log
- `logs/report_YYYY-MM-DD.log` — daily report output, one file per day
- `logs/launchd_stdout.log` — raw launchd output

---

## Scoring Categories

| Type | Categories |
|---|---|
| Batting | R, HR, RBI, SB, AVG, OPS |
| Pitching | W, SV, K, ERA, WHIP |

## Roster Slots

| Position | Slots |
|---|---|
| C, 1B, 2B, 3B, SS | 1 each |
| OF | 3 |
| Util | 2 |
| SP | 2 |
| RP | 2 |
| P (any pitcher) | 4 |
| BN | 5 |
| IL | 2 |

---

## Data Sources

- **Projections**: FanGraphs Steamer 2026 (cached in `.cache/`)
- **League data**: Yahoo Fantasy Sports API v2
- **Schedule**: MLB Stats API

Projection cache is stored in `.cache/` and refreshed on demand with `--refresh`.
