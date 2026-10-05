"""
Scrapes season schedules from basketball-reference.com - the pipeline's
second data source, alongside OddsPortal. Its official schedule is what
validate/ checks opponents against and what transform/ dates every game
from. scrape_season is the entry point: download every team's schedule page,
then parse it (parser.py). The pages are static HTML, so a plain download
does - unlike OddsPortal, no browser is needed.

Kept separate from parser.py so the parsing logic can be unit
tested against saved HTML fixtures with no network access, and so this
module's caching/politeness behavior can be changed without touching
parsing logic at all.
"""

import os
import time
import urllib.error
import urllib.request

from typing import Dict, List, Optional

from extract.basketball_reference.parser import ScheduleGame, parse_schedule_table, get_true_regular_season_games
from extract.basketball_reference.team_codes import TEAM_ABBR_TO_FULL_NAME

USER_AGENT = "Mozilla/5.0 (compatible; nba-moneyline-schedule-check/1.0)"
REQUEST_DELAY_SECONDS = 4  # be polite to basketball-reference's rate limits
MAX_FETCH_ATTEMPTS = 3


def fetch_team_schedule_html(abbr: str, season_start_year: int, cache_dir: str = None) -> tuple:
    """
    Fetch (or read from cache) the season-schedule page HTML for one team.

    Args:
        abbr: basketball-reference 3-letter team code (see team_codes.py)
        season_start_year: calendar year the season started (e.g. 2025 for 2025-26)
        cache_dir: if given, read/write a cached copy at {cache_dir}/{abbr}_{year}.html
                   instead of always hitting the network

    Returns:
        tuple: (html: str, was_cached: bool)
    """
    season_end_year = season_start_year + 1
    cache_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{abbr}_{season_end_year}.html")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read(), True

    url = f"https://www.basketball-reference.com/teams/{abbr}/{season_end_year}_games.html"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    html = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                html = response.read().decode("utf-8")
            break
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  ⚠️  Attempt {attempt}/{MAX_FETCH_ATTEMPTS} failed to fetch {abbr}'s schedule "
                  f"({e.__class__.__name__}: {e}), retrying...")
            if attempt < MAX_FETCH_ATTEMPTS:
                time.sleep(REQUEST_DELAY_SECONDS)
    else:
        raise RuntimeError(f"Failed to fetch {abbr}'s schedule after {MAX_FETCH_ATTEMPTS} attempts")

    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html, False


def fetch_all_team_schedules(season_start_year: int, cache_dir: str = None) -> dict:
    """
    Fetch every team's season-schedule HTML for a season.

    Returns dict of {team_full_name: html}. Fetches politely (a delay
    between requests) and skips already-cached teams instantly, so re-runs
    during development don't hammer basketball-reference.
    """
    html_by_team = {}
    for abbr, full_name in TEAM_ABBR_TO_FULL_NAME.items():
        html, was_cached = fetch_team_schedule_html(abbr, season_start_year, cache_dir=cache_dir)
        html_by_team[full_name] = html
        if not was_cached:
            time.sleep(REQUEST_DELAY_SECONDS)
    return html_by_team


def scrape_season(season: int, cache_dir: Optional[str] = None) -> Dict[str, List[ScheduleGame]]:
    """
    Every team's true regular-season games from basketball-reference (IST
    knockout and play-in games excluded), as {team_full_name: games in order}.

    Args:
        season: season_start_year (e.g. 2025 for the 2025-26 season)
        cache_dir: optional directory to cache fetched schedule HTML in,
                   so a re-run doesn't re-fetch from basketball-reference
    """
    html_by_team = fetch_all_team_schedules(season, cache_dir=cache_dir)
    return {team: get_true_regular_season_games(parse_schedule_table(html))
            for team, html in html_by_team.items()}
