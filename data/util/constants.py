"""
Expected per-team game counts for each NBA regular season, looked up by
season because the league's format has changed over the seasons this
project covers:

- Normal seasons: all 30 teams play 82 games. Since 2023-24 that includes
  the in-season tournament (NBA Cup): its group games, quarterfinals and
  semifinals all count toward the 82 (the final doesn't, and isn't scraped).
- 2019-20 (COVID): the season was suspended, then finished in the Orlando
  bubble with only 22 of the teams, so teams ended anywhere from 64 to 75
  games. There's no fixed pattern to check against - for that season, the
  cross-check against basketball-reference's schedule (which knows each
  team's real count) is the check.
- 2020-21 (COVID): a shortened 72-game season for every team.

Counts are per team, so a season's expected total is in team-game rows
(2 per game), the same unit the scraper uses.
"""

from typing import Dict, Optional

TEAMS_PER_LEAGUE = 30
BASELINE_GAMES_PER_TEAM = 82

COVID_BUBBLE_SEASON = 2019            # 2019-20: uneven per-team counts
COVID_SHORTENED_SEASON = 2020         # 2020-21: 72 games each
COVID_SHORTENED_GAMES_PER_TEAM = 72
FIRST_IST_SEASON = 2023               # 2023-24: first in-season tournament (NBA Cup);
                                      # its knockout games are scraped from a separate page


def expected_game_count_distribution(season: int) -> Optional[Dict[int, int]]:
    """
    Expected per-team game count -> how many teams should land on that count,
    for the season starting in `season`. None when the season has no fixed
    pattern (2019-20), meaning the count check doesn't apply.

    Note: this only checks *counts*, not which specific teams they belong to.
    """
    if season == COVID_BUBBLE_SEASON:
        return None
    if season == COVID_SHORTENED_SEASON:
        return {COVID_SHORTENED_GAMES_PER_TEAM: TEAMS_PER_LEAGUE}
    return {BASELINE_GAMES_PER_TEAM: TEAMS_PER_LEAGUE}


def expected_total_rows(distribution: Dict[int, int]) -> int:
    """Total team-game rows a season with this distribution should have."""
    return sum(games * teams for games, teams in distribution.items())
