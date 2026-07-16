"""
Verifies the quality of scraped moneyline data before it's trusted enough
to migrate to production, two ways:

- verify_scraped_data: total and per-team game counts against a hardcoded,
  independently-derived expectation (see util/constants.py) - fast, no
  network access.
- validate_scraped_data_against_schedule: per-team, per-opponent game
  counts against basketball-reference's authoritative schedule. Comparison
  is order-agnostic (multiset of opponents, not sequence): OddsPortal and
  basketball-reference can legitimately disagree on a game's exact
  chronological position in the odd case where the game was postponed and
  replayed on a different date, so we only check *which* opponents (and
  how many times each) a team played, not what order they appear in.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from migrate.bbref.fetcher import fetchAllTeamSchedules
from migrate.bbref.parser import parseScheduleTable, getTrueRegularSeasonOpponents
from util.constants import TOTAL_EXPECTED_GAMES, EXPECTED_GAME_COUNT_DISTRIBUTION


def verify_scraped_data(db_path: str, season: int) -> Dict:
    """
    Verify scraped data in SQLite database.

    Returns dict with:
        - total_games: int
        - team_counts: list of (team, count) tuples
        - total_games_ok: bool (matches TOTAL_EXPECTED_GAMES)
        - distribution_ok: bool (per-team counts match the expected
          82/81/80 distribution accounting for the in-season tournament,
          see util/constants.py)
        - unexpected_teams: list of (team, count) tuples whose count isn't
          82, 81, or 80 at all
        - distribution_mismatch: dict of {expected_count: (expected_teams, actual_teams)}
          for counts that exist in the distribution but with the wrong number of teams
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get total game count
    cursor.execute("SELECT COUNT(*) FROM games WHERE seasonStartYear = ?", (season,))
    total_games = cursor.fetchone()[0]

    # Get game count per team
    cursor.execute("""
        SELECT team, COUNT(*) as game_count
        FROM games
        WHERE seasonStartYear = ?
        GROUP BY team
        ORDER BY team
    """, (season,))
    team_counts = cursor.fetchall()

    conn.close()

    count_tally = Counter(count for _, count in team_counts)

    unexpected_teams = [(team, count) for team, count in team_counts
                        if count not in EXPECTED_GAME_COUNT_DISTRIBUTION]

    distribution_mismatch = {}
    for expected_count, expected_teams in EXPECTED_GAME_COUNT_DISTRIBUTION.items():
        actual_teams = count_tally.get(expected_count, 0)
        if actual_teams != expected_teams:
            distribution_mismatch[expected_count] = (expected_teams, actual_teams)

    return {
        'total_games': total_games,
        'team_counts': team_counts,
        'total_games_ok': total_games == TOTAL_EXPECTED_GAMES,
        'distribution_ok': not unexpected_teams and not distribution_mismatch,
        'unexpected_teams': unexpected_teams,
        'distribution_mismatch': distribution_mismatch,
    }


@dataclass
class TeamScheduleComparison:
    team: str
    true_game_count: int
    scraped_game_count: int
    missing_opponents: Counter  # in the true schedule but missing (or short) from our scrape
    extra_opponents: Counter    # in our scrape but not in the true schedule (or too many times)

    @property
    def ok(self) -> bool:
        return not self.missing_opponents and not self.extra_opponents


def compare_opponent_multisets(true_opponents: List[str], scraped_opponents: List[str]) -> Dict[str, Counter]:
    """Order-agnostic diff of two opponent lists. Pure function, no I/O."""
    true_counts = Counter(true_opponents)
    scraped_counts = Counter(scraped_opponents)
    return {
        "missing": true_counts - scraped_counts,
        "extra": scraped_counts - true_counts,
    }


def get_scraped_opponents(db_path: str, season: int, team_full_name: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT opponent FROM games
        WHERE team = ? AND seasonStartYear = ?
        ORDER BY gameNumber
    """, (team_full_name, season))
    opponents = [row[0] for row in cursor.fetchall()]
    conn.close()
    return opponents


def validate_scraped_data_against_schedule(db_path: str, season: int,
                                            cache_dir: Optional[str] = None) -> List[TeamScheduleComparison]:
    """
    Compare every team's scraped opponents against basketball-reference's
    authoritative schedule (IST knockout and play-in games excluded).

    Args:
        db_path: path to the season's SQLite database
        season: seasonStartYear (e.g. 2025 for the 2025-26 season)
        cache_dir: optional directory to cache fetched schedule HTML in,
                   so repeated runs (e.g. during development) don't
                   re-fetch from basketball-reference every time
    """
    html_by_team = fetchAllTeamSchedules(season, cache_dir=cache_dir)

    results = []
    for team_full_name, html in html_by_team.items():
        games = parseScheduleTable(html)
        true_opponents = getTrueRegularSeasonOpponents(games)
        scraped_opponents = get_scraped_opponents(db_path, season, team_full_name)

        diff = compare_opponent_multisets(true_opponents, scraped_opponents)
        results.append(TeamScheduleComparison(
            team=team_full_name,
            true_game_count=len(true_opponents),
            scraped_game_count=len(scraped_opponents),
            missing_opponents=diff["missing"],
            extra_opponents=diff["extra"],
        ))
    return results
