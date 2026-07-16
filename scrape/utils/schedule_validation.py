"""
Validates scraped moneyline data against basketball-reference's authoritative
season schedule, per team.

Comparison is order-agnostic (multiset of opponents, not sequence): OddsPortal
and basketball-reference can legitimately disagree on a game's exact
chronological position in the odd case where the game was postponed and
replayed on a different date, so we only check *which* opponents (and how
many times each) a team played, not what order they appear in.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from basketball_reference.schedule_fetcher import fetchAllTeamSchedules
from basketball_reference.schedule_parser import parseScheduleTable, getTrueRegularSeasonOpponents


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
