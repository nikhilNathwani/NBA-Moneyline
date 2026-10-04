"""
Expected per-team game counts for each NBA regular season, looked up by
season because the league's format has changed over the seasons this
project covers:

- Normal seasons: all 30 teams play 82 games.
- 2019-20 (COVID): the season was suspended, then finished in the Orlando
  bubble with only 22 of the teams, so teams ended anywhere from 64 to 75
  games. There's no fixed pattern to check against - for that season, the
  cross-check against basketball-reference's schedule (which knows each
  team's real count) is the check.
- 2020-21 (COVID): a shortened 72-game season for every team.
- 2023-24 onward: the in-season tournament (IST, later the NBA Cup). Its
  knockout-round games count as part of a team's official game log, but
  this project treats them as noise and excludes them from scraping (no
  clean single-opponent moneyline, neutral-site, etc.), so not every team
  lands on 82:
    - The 4 teams eliminated in the IST quarterfinals (round of 8) each have
      1 excluded game (the quarterfinal itself) -> 81 games.
    - The 4 teams that reach the IST semifinals (the Vegas "final four")
      each have 2 excluded games (semifinal + championship-or-3rd-place)
      -> 80 games.
    - The other 22 teams are untouched at 82.
  That's 30*82 - (4*1 + 4*2) = 2460 - 12 = 2448 team-game rows.

Counts are per team, so a season's expected total is in team-game rows
(2 per game), the same unit the scraper and the games table use.
"""

from typing import Dict, Optional

TEAMS_PER_LEAGUE = 30
BASELINE_GAMES_PER_TEAM = 82

COVID_BUBBLE_SEASON = 2019            # 2019-20: uneven per-team counts
COVID_SHORTENED_SEASON = 2020         # 2020-21: 72 games each
COVID_SHORTENED_GAMES_PER_TEAM = 72
FIRST_IST_SEASON = 2023               # 2023-24: first in-season tournament

IST_QUARTERFINALIST_COUNT = 4   # teams eliminated in the IST round of 8
IST_QUARTERFINALIST_EXPECTED_GAMES = BASELINE_GAMES_PER_TEAM - 1  # 81
IST_SEMIFINALIST_COUNT = 4      # teams that reach the IST semifinals (Vegas final four)
IST_SEMIFINALIST_EXPECTED_GAMES = BASELINE_GAMES_PER_TEAM - 2     # 80
IST_UNAFFECTED_TEAM_COUNT = TEAMS_PER_LEAGUE - IST_QUARTERFINALIST_COUNT - IST_SEMIFINALIST_COUNT  # 22


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
    if season >= FIRST_IST_SEASON:
        return {
            BASELINE_GAMES_PER_TEAM: IST_UNAFFECTED_TEAM_COUNT,
            IST_QUARTERFINALIST_EXPECTED_GAMES: IST_QUARTERFINALIST_COUNT,
            IST_SEMIFINALIST_EXPECTED_GAMES: IST_SEMIFINALIST_COUNT,
        }
    return {BASELINE_GAMES_PER_TEAM: TEAMS_PER_LEAGUE}


def expected_total_rows(distribution: Dict[int, int]) -> int:
    """Total team-game rows a season with this distribution should have."""
    return sum(games * teams for games, teams in distribution.items())
