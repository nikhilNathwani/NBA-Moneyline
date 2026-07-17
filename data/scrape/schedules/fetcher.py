"""
Fetches raw season-schedule HTML from basketball-reference.com.

Kept separate from parser.py so the parsing logic can be unit
tested against saved HTML fixtures with no network access, and so this
module's caching/politeness behavior can be changed without touching
parsing logic at all.
"""

import os
import time
import urllib.error
import urllib.request

from scrape.schedules.team_codes import TEAM_ABBR_TO_FULL_NAME

USER_AGENT = "Mozilla/5.0 (compatible; nba-moneyline-schedule-check/1.0)"
REQUEST_DELAY_SECONDS = 4  # be polite to basketball-reference's rate limits
MAX_FETCH_ATTEMPTS = 3


def fetchTeamScheduleHtml(abbr: str, seasonStartYear: int, cache_dir: str = None) -> tuple:
    """
    Fetch (or read from cache) the season-schedule page HTML for one team.

    Args:
        abbr: basketball-reference 3-letter team code (see team_codes.py)
        seasonStartYear: calendar year the season started (e.g. 2025 for 2025-26)
        cache_dir: if given, read/write a cached copy at {cache_dir}/{abbr}_{year}.html
                   instead of always hitting the network

    Returns:
        tuple: (html: str, was_cached: bool)
    """
    season_end_year = seasonStartYear + 1
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


def fetchAllTeamSchedules(seasonStartYear: int, cache_dir: str = None) -> dict:
    """
    Fetch every team's season-schedule HTML for a season.

    Returns dict of {team_full_name: html}. Fetches politely (a delay
    between requests) and skips already-cached teams instantly, so re-runs
    during development don't hammer basketball-reference.
    """
    html_by_team = {}
    for abbr, full_name in TEAM_ABBR_TO_FULL_NAME.items():
        html, was_cached = fetchTeamScheduleHtml(abbr, seasonStartYear, cache_dir=cache_dir)
        html_by_team[full_name] = html
        if not was_cached:
            time.sleep(REQUEST_DELAY_SECONDS)
    return html_by_team
