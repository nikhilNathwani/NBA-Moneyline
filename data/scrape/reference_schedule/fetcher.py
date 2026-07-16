"""
Fetches raw season-schedule HTML from basketball-reference.com.

Kept separate from parser.py so the parsing logic can be unit
tested against saved HTML fixtures with no network access, and so this
module's caching/politeness behavior can be changed without touching
parsing logic at all.
"""

import os
import time
import urllib.request

from scrape.reference_schedule.team_codes import TEAM_ABBR_TO_FULL_NAME

USER_AGENT = "Mozilla/5.0 (compatible; nba-moneyline-schedule-check/1.0)"
REQUEST_DELAY_SECONDS = 4  # be polite to basketball-reference's rate limits


def fetchTeamScheduleHtml(abbr: str, seasonStartYear: int, cache_dir: str = None) -> str:
    """
    Fetch (or read from cache) the season-schedule page HTML for one team.

    Args:
        abbr: basketball-reference 3-letter team code (see team_codes.py)
        seasonStartYear: calendar year the season started (e.g. 2025 for 2025-26)
        cache_dir: if given, read/write a cached copy at {cache_dir}/{abbr}_{year}.html
                   instead of always hitting the network
    """
    season_end_year = seasonStartYear + 1
    cache_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{abbr}_{season_end_year}.html")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read()

    url = f"https://www.basketball-reference.com/teams/{abbr}/{season_end_year}_games.html"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        html = response.read().decode("utf-8")

    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html


def fetchAllTeamSchedules(seasonStartYear: int, cache_dir: str = None) -> dict:
    """
    Fetch every team's season-schedule HTML for a season.

    Returns dict of {team_full_name: html}. Fetches politely (a delay
    between requests) and skips already-cached teams instantly, so re-runs
    during development don't hammer basketball-reference.
    """
    html_by_team = {}
    for abbr, full_name in TEAM_ABBR_TO_FULL_NAME.items():
        was_cached = cache_dir and os.path.exists(
            os.path.join(cache_dir, f"{abbr}_{seasonStartYear + 1}.html")
        )
        html_by_team[full_name] = fetchTeamScheduleHtml(abbr, seasonStartYear, cache_dir=cache_dir)
        if not was_cached:
            time.sleep(REQUEST_DELAY_SECONDS)
    return html_by_team
