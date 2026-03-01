"""CLI entry point for the baseball manager."""
import click
from tabulate import tabulate


@click.group()
def main():
    """Yahoo Fantasy Baseball AI Manager."""
    pass


@main.command()
def auth():
    """Authorize with Yahoo (run once to get OAuth token)."""
    from baseball_manager.auth.yahoo_oauth import authorize
    authorize()


@main.command()
def status():
    """Show league info, standings, and current matchup."""
    from baseball_manager.api.yahoo_client import YahooClient
    client = YahooClient()

    click.echo("\n=== League Info ===")
    info = client.get_league_info()
    click.echo(f"  Name:   {info.get('name')}")
    click.echo(f"  Season: {info.get('season')}")
    click.echo(f"  Teams:  {info.get('num_teams')}")
    click.echo(f"  Week:   {info.get('current_week')}")

    click.echo("\n=== My Team ===")
    teams = client.get_teams()
    my_key = client.get_my_team_key()
    for team in teams:
        if team.get("team_key") == my_key:
            click.echo(f"  {team.get('name')} (Manager: {team.get('managers', {}).get('manager', {}).get('nickname', 'unknown')})")
            break

    click.echo("\n=== Current Roster ===")
    roster = client.get_my_roster()
    rows = []
    for p in roster:
        name = p.get("name", {}).get("full", "?")
        pos = p.get("selected_position", {}).get("position", "?")
        eligible = p.get("eligible_positions", {}).get("position", "?")
        if isinstance(eligible, list):
            eligible = ", ".join(eligible)
        rows.append([pos, name, eligible])
    click.echo(tabulate(rows, headers=["Slot", "Player", "Eligible Positions"]))


@main.command()
def roster():
    """Show current roster with positions."""
    from baseball_manager.api.yahoo_client import YahooClient
    client = YahooClient()
    players = client.get_my_roster()
    rows = []
    for p in players:
        name = p.get("name", {}).get("full", "?")
        pos = p.get("selected_position", {}).get("position", "?")
        team = p.get("editorial_team_abbr", "?")
        status = p.get("status", "")
        rows.append([pos, name, team, status])
    click.echo(tabulate(rows, headers=["Slot", "Player", "MLB Team", "Status"]))


@main.command()
def matchup():
    """Show current week's matchup stats."""
    from baseball_manager.api.yahoo_client import YahooClient
    client = YahooClient()
    m = client.get_my_matchup()
    if not m:
        click.echo("No active matchup found.")
        return
    teams = m.get("teams", {}).get("team", [])
    if not isinstance(teams, list):
        teams = [teams]
    for team in teams:
        name = team.get("name", "?")
        stats = team.get("team_stats", {}).get("stats", {}).get("stat", [])
        if not isinstance(stats, list):
            stats = [stats]
        click.echo(f"\n  {name}")
        for stat in stats:
            click.echo(f"    {stat.get('stat_id')}: {stat.get('value')}")


def _load_ranked_roster(client):
    """Fetch Yahoo roster and enrich with projection z-scores."""
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings

    yahoo_roster = client.get_my_roster()
    raw_bat = get_batting_projections()
    raw_pit = get_pitching_projections()
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    all_ranked = build_unified_rankings(batters, pitchers)

    # Match Yahoo roster players to ranked projections by name
    ranked_by_name = {p["name"].lower(): p for p in all_ranked}
    roster = []
    for yp in yahoo_roster:
        name = yp.get("name", {}).get("full", "")
        matched = ranked_by_name.get(name.lower(), {})
        player = {
            "name": name,
            "team": yp.get("editorial_team_abbr", "?"),
            "status": yp.get("status", ""),
            "selected_position": yp.get("selected_position", {}),
            "positions": matched.get("positions", ["Util"]),
            "player_type": matched.get("player_type", "batter"),
            "proj": matched.get("proj", {}),
            "z_norm": matched.get("z_norm", 0.0),
            "z_total": matched.get("z_total", 0.0),
        }
        roster.append(player)
    return roster


@main.command()
@click.option("--date", "date_str", default=None, help="Date YYYY-MM-DD (default: today)")
def lineup(date_str):
    """Show recommended lineup for today (or a specific date)."""
    from datetime import date as dt
    from baseball_manager.api.yahoo_client import YahooClient
    from baseball_manager.data.mlb_schedule import get_playing_teams
    from baseball_manager.lineup.optimizer import optimize_lineup, format_lineup, lineup_changes

    target_date = dt.fromisoformat(date_str) if date_str else dt.today()
    client = YahooClient()

    click.echo(f"\nFetching roster and schedule for {target_date.isoformat()}...")
    roster = _load_ranked_roster(client)
    playing_teams = get_playing_teams(target_date)

    click.echo(f"  {len(playing_teams)} MLB teams playing today\n")

    optimal = optimize_lineup(roster, playing_teams, date_str=target_date.isoformat())

    click.echo("=== RECOMMENDED LINEUP ===\n")
    click.echo(format_lineup(optimal, playing_teams))

    changes = lineup_changes(roster, optimal)
    if changes:
        click.echo("\n=== MOVES TO MAKE ON YAHOO ===")
        for c in changes:
            click.echo(c)
    else:
        click.echo("\nNo lineup changes needed.")


@main.command()
@click.option("--position", "-p", default=None, help="Filter by position")
@click.option("--top", "-n", default=15, show_default=True)
def waivers(position, top):
    """Show top waiver wire pickups and drop candidates."""
    from baseball_manager.api.yahoo_client import YahooClient
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings
    from baseball_manager.roster.waivers import find_pickup_targets, find_drop_candidates, format_pickups, format_drops

    client = YahooClient()
    click.echo("Fetching roster and free agents...")

    my_roster = _load_ranked_roster(client)
    raw_bat = get_batting_projections()
    raw_pit = get_pitching_projections()
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    all_ranked = build_unified_rankings(batters, pitchers)

    # Fetch free agents from Yahoo (multiple pages)
    fa_names = set()
    free_agents_raw = []
    for start in range(0, 150, 25):
        page = client.search_players(status="FA", start=start, count=25)
        if not page:
            break
        for yp in page:
            name = yp.get("name", {}).get("full", "")
            if name and name not in fa_names:
                fa_names.add(name)
                free_agents_raw.append(name)

    ranked_by_name = {p["name"].lower(): p for p in all_ranked}
    free_agents = [
        ranked_by_name[n.lower()]
        for n in free_agents_raw
        if n.lower() in ranked_by_name
    ]

    click.echo(f"  {len(free_agents)} free agents found with projections\n")

    click.echo("=== TOP PICKUP TARGETS ===\n")
    targets = find_pickup_targets(my_roster, free_agents, top_n=top, position=position)
    click.echo(format_pickups(targets))

    click.echo("\n=== DROP CANDIDATES (your weakest holds) ===\n")
    drops = find_drop_candidates(my_roster, top_n=5)
    click.echo(format_drops(drops))


@main.command()
def report():
    """Full daily report: matchup, lineup recommendation, and waiver targets."""
    from datetime import date as dt
    from baseball_manager.api.yahoo_client import YahooClient
    from baseball_manager.data.mlb_schedule import get_playing_teams
    from baseball_manager.lineup.optimizer import optimize_lineup, format_lineup
    from baseball_manager.roster.waivers import find_pickup_targets, find_drop_candidates, format_pickups, format_drops
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings

    today = dt.today()
    client = YahooClient()

    click.echo(f"\n{'='*60}")
    click.echo(f"  COOL GUYS DAILY REPORT — {today.strftime('%A, %B %-d, %Y')}")
    click.echo(f"{'='*60}\n")

    # Matchup
    click.echo("--- CURRENT MATCHUP ---")
    try:
        m = client.get_my_matchup()
        if m:
            teams = m.get("teams", {}).get("team", [])
            if not isinstance(teams, list):
                teams = [teams]
            for team in teams:
                name = team.get("name", "?")
                stats = team.get("team_stats", {}).get("stats", {}).get("stat", [])
                if not isinstance(stats, list):
                    stats = [stats]
                click.echo(f"  {name}")
        else:
            click.echo("  No active matchup.")
    except Exception as e:
        click.echo(f"  (matchup unavailable: {e})")

    # Lineup
    click.echo("\n--- TODAY'S LINEUP ---")
    roster = _load_ranked_roster(client)
    playing_teams = get_playing_teams(today)
    optimal = optimize_lineup(roster, playing_teams)
    click.echo(format_lineup(optimal, playing_teams))

    # Waivers
    click.echo("\n--- TOP WAIVER TARGETS ---")
    raw_bat = get_batting_projections()
    raw_pit = get_pitching_projections()
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    all_ranked = build_unified_rankings(batters, pitchers)
    ranked_by_name = {p["name"].lower(): p for p in all_ranked}

    fa_names: set[str] = set()
    free_agents_raw = []
    for start in range(0, 75, 25):
        page = client.search_players(status="FA", start=start, count=25)
        if not page:
            break
        for yp in page:
            name = yp.get("name", {}).get("full", "")
            if name and name not in fa_names:
                fa_names.add(name)
                free_agents_raw.append(name)

    free_agents = [ranked_by_name[n.lower()] for n in free_agents_raw if n.lower() in ranked_by_name]
    targets = find_pickup_targets(roster, free_agents, top_n=8)
    click.echo(format_pickups(targets))

    click.echo("\n--- DROP CANDIDATES ---")
    drops = find_drop_candidates(roster, top_n=3)
    click.echo(format_drops(drops))


@main.command()
@click.option("--refresh", is_flag=True, help="Re-fetch projections from FanGraphs")
@click.option("--pick", default=11, show_default=True, help="Your draft slot (1-12)")
def draft(refresh, pick):
    """Launch the interactive draft assistant."""
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings
    from baseball_manager.draft.board import DraftBoard

    click.echo("Loading projections...")
    raw_bat = get_batting_projections(force_refresh=refresh)
    raw_pit = get_pitching_projections(force_refresh=refresh)

    click.echo("Calculating fantasy values...")
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    rankings = build_unified_rankings(batters, pitchers)

    click.echo(f"  {len(batters)} batters | {len(pitchers)} pitchers | {len(rankings)} total ranked\n")

    board = DraftBoard(rankings, num_teams=12, my_pick=pick, num_rounds=25)
    board.run()


@main.command()
@click.option("--refresh", is_flag=True, help="Re-fetch projections from FanGraphs")
@click.option("--position", "-p", default=None, help="Filter by position (C, 1B, SS, OF, SP, RP...)")
@click.option("--top", "-n", default=50, show_default=True, help="Number of players to show")
@click.option("--type", "-t", "player_type", default="all", type=click.Choice(["all", "bat", "pit"]))
def rankings(refresh, position, top, player_type):
    """Show pre-draft player rankings."""
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings

    raw_bat = get_batting_projections(force_refresh=refresh)
    raw_pit = get_pitching_projections(force_refresh=refresh)
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    all_players = build_unified_rankings(batters, pitchers)

    if player_type == "bat":
        players = [p for p in all_players if p["player_type"] == "batter"]
    elif player_type == "pit":
        players = [p for p in all_players if p["player_type"] == "pitcher"]
    else:
        players = all_players

    if position:
        players = [p for p in players if position.upper() in p["positions"]]

    players = players[:top]
    rows = []
    for p in players:
        proj = p.get("proj", {})
        if p["player_type"] == "batter":
            stats = (f"R:{proj.get('R',0):.0f} HR:{proj.get('HR',0):.0f} "
                     f"RBI:{proj.get('RBI',0):.0f} SB:{proj.get('SB',0):.0f} "
                     f"AVG:{proj.get('AVG',0):.3f} OPS:{proj.get('OPS',0):.3f}")
        else:
            stats = (f"W:{proj.get('W',0):.0f} SV:{proj.get('SV',0):.0f} "
                     f"K:{proj.get('K',0):.0f} ERA:{proj.get('ERA',0):.2f} "
                     f"WHIP:{proj.get('WHIP',0):.3f}")
        rows.append([
            p["overall_rank"],
            p["name"],
            p["team"],
            "/".join(p["positions"]),
            round(p["z_norm"], 2),
            stats,
        ])
    click.echo(tabulate(rows, headers=["Rank", "Name", "Team", "Pos", "zVal", "Projections"]))


@main.group()
def scheduler():
    """Manage the daily report scheduler (macOS launchd)."""
    pass


@scheduler.command("install")
@click.option("--time", "run_time", default="08:00", show_default=True,
              help="Time to run daily report (24h HH:MM)")
def scheduler_install(run_time):
    """Install the daily scheduler via macOS launchd."""
    from baseball_manager.scripts.launchd import install
    install(run_time)


@scheduler.command("uninstall")
def scheduler_uninstall():
    """Remove the daily scheduler."""
    from baseball_manager.scripts.launchd import uninstall
    uninstall()


@scheduler.command("status")
def scheduler_status():
    """Show whether the scheduler is running and recent log output."""
    from baseball_manager.scripts.launchd import status
    status()


@scheduler.command("run")
@click.option("--time", "run_time", default="08:00", show_default=True,
              help="Time to run daily report (24h HH:MM)")
def scheduler_run(run_time):
    """Run the scheduler daemon in the foreground (for testing)."""
    from baseball_manager.scripts.scheduler import run_daemon
    run_daemon(run_time)


@scheduler.command("now")
def scheduler_now():
    """Run the daily report immediately (one-shot, no daemon)."""
    from baseball_manager.scripts.scheduler import run_daily_report, _setup_logging
    _setup_logging()
    run_daily_report()


@main.group()
def automate():
    """Browser automation for Yahoo lineup and waiver moves."""
    pass


def _require_cookies():
    """Exit with a helpful message if the cookie file is missing."""
    from baseball_manager.browser.yahoo_browser import COOKIES_FILE
    if not COOKIES_FILE.exists():
        click.echo("No saved session found. Run `bbm automate login` first.")
        raise SystemExit(1)


@automate.command("login")
def automate_login():
    """Open a browser window for Yahoo login and save the session cookie."""
    from baseball_manager.browser.yahoo_browser import YahooBrowser
    YahooBrowser.login()


@automate.command("lineup")
@click.option("--date", "date_str", default=None, help="Date YYYY-MM-DD (default: today)")
@click.option("--dry-run", is_flag=True, help="Print moves without executing them")
@click.option("--headed", is_flag=True, help="Show browser window (for debugging)")
def automate_lineup(date_str, dry_run, headed):
    """Fetch optimal lineup and apply it on Yahoo."""
    from datetime import date as dt
    from baseball_manager.api.yahoo_client import YahooClient
    from baseball_manager.data.mlb_schedule import get_playing_teams
    from baseball_manager.lineup.optimizer import optimize_lineup, format_lineup, lineup_changes

    target_date = dt.fromisoformat(date_str) if date_str else dt.today()
    client = YahooClient()

    click.echo(f"\nFetching roster and schedule for {target_date.isoformat()}...")
    roster = _load_ranked_roster(client)
    playing_teams = get_playing_teams(target_date)
    click.echo(f"  {len(playing_teams)} MLB teams playing today\n")

    optimal = optimize_lineup(roster, playing_teams, date_str=target_date.isoformat())
    changes = lineup_changes(roster, optimal)

    click.echo("=== RECOMMENDED LINEUP ===\n")
    click.echo(format_lineup(optimal, playing_teams))

    if not changes:
        click.echo("\nNo lineup changes needed.")
        return

    click.echo("\n=== MOVES TO MAKE ===")
    for c in changes:
        click.echo(c)

    if dry_run:
        click.echo("\n[dry-run] No changes applied.")
        return

    _require_cookies()

    from baseball_manager.browser.yahoo_browser import YahooBrowser
    from baseball_manager.browser.lineup_setter import LineupSetter

    click.echo("\nApplying lineup changes via browser...")
    with YahooBrowser(headless=not headed) as browser:
        setter = LineupSetter(browser)
        moves = setter.set_lineup(target_date.isoformat(), optimal)

    if moves:
        click.echo("\n=== APPLIED MOVES ===")
        for m in moves:
            click.echo(m)
    else:
        click.echo("No moves were applied.")


@automate.command("add")
@click.argument("player_name")
@click.option("--drop", "drop_name", default=None, help="Player to drop (if roster full)")
@click.option("--headed", is_flag=True, help="Show browser window (for debugging)")
def automate_add(player_name, drop_name, headed):
    """Add a free agent to your roster, optionally dropping another player."""
    _require_cookies()

    from baseball_manager.browser.yahoo_browser import YahooBrowser
    from baseball_manager.browser.transactions import TransactionManager

    with YahooBrowser(headless=not headed) as browser:
        tm = TransactionManager(browser)
        success = tm.add_player(player_name, drop_name)

    if success:
        msg = f"Added {player_name}"
        if drop_name:
            msg += f", dropped {drop_name}"
        click.echo(msg)
    else:
        click.echo(f"Failed to add {player_name}. Check logs/screenshots/ for details.")
        raise SystemExit(1)


@automate.command("drop")
@click.argument("player_name")
@click.option("--headed", is_flag=True, help="Show browser window (for debugging)")
def automate_drop(player_name, headed):
    """Drop a player from your roster."""
    _require_cookies()

    from baseball_manager.browser.yahoo_browser import YahooBrowser
    from baseball_manager.browser.transactions import TransactionManager

    with YahooBrowser(headless=not headed) as browser:
        tm = TransactionManager(browser)
        success = tm.drop_player(player_name)

    if success:
        click.echo(f"Dropped {player_name}")
    else:
        click.echo(f"Failed to drop {player_name}. Check logs/screenshots/ for details.")
        raise SystemExit(1)


@automate.command("waivers")
@click.option("--dry-run", is_flag=True, help="Show what would happen without executing")
@click.option("--headed", is_flag=True, help="Show browser window (for debugging)")
def automate_waivers(dry_run, headed):
    """Execute the top waiver pickup and drop the weakest roster player."""
    from baseball_manager.api.yahoo_client import YahooClient
    from baseball_manager.data.fangraphs import get_batting_projections, get_pitching_projections
    from baseball_manager.draft.values import calculate_batter_values, calculate_pitcher_values, build_unified_rankings
    from baseball_manager.roster.waivers import find_pickup_targets, find_drop_candidates

    client = YahooClient()
    click.echo("Fetching roster and free agents...")

    my_roster = _load_ranked_roster(client)
    raw_bat = get_batting_projections()
    raw_pit = get_pitching_projections()
    batters = calculate_batter_values(raw_bat)
    pitchers = calculate_pitcher_values(raw_pit)
    all_ranked = build_unified_rankings(batters, pitchers)

    fa_names: set[str] = set()
    free_agents_raw: list[str] = []
    for start in range(0, 75, 25):
        page = client.search_players(status="FA", start=start, count=25)
        if not page:
            break
        for yp in page:
            name = yp.get("name", {}).get("full", "")
            if name and name not in fa_names:
                fa_names.add(name)
                free_agents_raw.append(name)

    ranked_by_name = {p["name"].lower(): p for p in all_ranked}
    free_agents = [ranked_by_name[n.lower()] for n in free_agents_raw if n.lower() in ranked_by_name]

    targets = find_pickup_targets(my_roster, free_agents, top_n=1)
    drops = find_drop_candidates(my_roster, top_n=1)

    if not targets:
        click.echo("No pickup targets found above current roster quality.")
        return
    if not drops:
        click.echo("No drop candidates found.")
        return

    add_name = targets[0]["name"]
    drop_name = drops[0]["name"]

    click.echo(f"\nProposed transaction:")
    click.echo(f"  ADD:  {add_name}")
    click.echo(f"  DROP: {drop_name}")

    if dry_run:
        click.echo("\n[dry-run] No changes applied.")
        return

    _require_cookies()

    from baseball_manager.browser.yahoo_browser import YahooBrowser
    from baseball_manager.browser.transactions import TransactionManager

    click.echo("\nExecuting transaction via browser...")
    with YahooBrowser(headless=not headed) as browser:
        tm = TransactionManager(browser)
        success = tm.add_player(add_name, drop_name=drop_name)

    if success:
        click.echo(f"Done: added {add_name}, dropped {drop_name}")
    else:
        click.echo("Transaction failed. Check logs/screenshots/ for details.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
