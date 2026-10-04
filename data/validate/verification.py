"""
Verifies the quality of scraped moneyline data before it's trusted enough
to migrate to production, two ways:

- verify_scraped_data: total and per-team game counts against a hardcoded,
  independently-derived expectation for that season (see util/constants.py)
  - fast, no network access.
- validate_scraped_data_against_schedule: per-team, per-opponent game
  counts against basketball-reference's authoritative schedule. Comparison
  is order-agnostic (multiset of opponents, not sequence): OddsPortal and
  basketball-reference can legitimately disagree on a game's exact
  chronological position in the odd case where the game was postponed and
  replayed on a different date, so we only check *which* opponents (and
  how many times each) a team played, not what order they appear in.

Both work directly on the scraper's in-memory output - there's no
intermediate storage to verify against.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from validate.schedules.fetcher import fetchAllTeamSchedules
from validate.schedules.parser import parseScheduleTable, getTrueRegularSeasonOpponents
from util.constants import expected_game_count_distribution, expected_total_rows
from util.game import Game


def verify_scraped_data(team_games: Dict[str, List[Game]], season: int) -> Dict:
    """
    Verify scraped data straight from the scraper's output against the
    season's expected per-team game counts (see util/constants.py).

    Returns dict with:
        - total_games: int (team-game rows, 2 per game)
        - team_counts: list of (team, count) tuples
        - expected_distribution: {games: teams} for this season, or None if
          the season has no fixed pattern (2019-20) - then the three results
          below are None too, meaning "not applicable", not "passed"
        - expected_total: int or None
        - total_games_ok: bool or None (matches expected_total)
        - distribution_ok: bool or None (per-team counts match
          expected_distribution)
        - unexpected_teams: list of (team, count) tuples whose count isn't
          in expected_distribution at all
        - distribution_mismatch: dict of {expected_count: (expected_teams, actual_teams)}
          for counts that exist in the distribution but with the wrong number of teams
    """
    team_counts = sorted((team, len(games)) for team, games in team_games.items())
    total_games = sum(count for _, count in team_counts)
    results = {
        'total_games': total_games,
        'team_counts': team_counts,
        'expected_distribution': None,
        'expected_total': None,
        'total_games_ok': None,
        'distribution_ok': None,
        'unexpected_teams': [],
        'distribution_mismatch': {},
    }

    distribution = expected_game_count_distribution(season)
    if distribution is None:
        return results

    count_tally = Counter(count for _, count in team_counts)

    unexpected_teams = [(team, count) for team, count in team_counts
                        if count not in distribution]

    distribution_mismatch = {}
    for expected_count, expected_teams in distribution.items():
        actual_teams = count_tally.get(expected_count, 0)
        if actual_teams != expected_teams:
            distribution_mismatch[expected_count] = (expected_teams, actual_teams)

    expected_total = expected_total_rows(distribution)
    results.update({
        'expected_distribution': distribution,
        'expected_total': expected_total,
        'total_games_ok': total_games == expected_total,
        'distribution_ok': not unexpected_teams and not distribution_mismatch,
        'unexpected_teams': unexpected_teams,
        'distribution_mismatch': distribution_mismatch,
    })
    return results


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


def validate_scraped_data_against_schedule(team_games: Dict[str, List[Game]], season: int,
                                            cache_dir: Optional[str] = None) -> List[TeamScheduleComparison]:
    """
    Compare every team's scraped opponents against basketball-reference's
    authoritative schedule (IST knockout and play-in games excluded).

    Args:
        team_games: scraped games straight from the scraper's output
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
        scraped_opponents = [g.opponent for g in team_games.get(team_full_name, [])]

        diff = compare_opponent_multisets(true_opponents, scraped_opponents)
        results.append(TeamScheduleComparison(
            team=team_full_name,
            true_game_count=len(true_opponents),
            scraped_game_count=len(scraped_opponents),
            missing_opponents=diff["missing"],
            extra_opponents=diff["extra"],
        ))
    return results
