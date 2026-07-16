"""
Expected game-count constants for a standard NBA regular season.

The NBA in-season tournament (IST) knockout round plays some games that
count as part of a team's official game log but that this project treats
as noise and excludes from scraping (no clean single-opponent moneyline,
neutral-site, etc.). That means not every team should have the same game
count once excluded:

- Most teams: the full 82-game regular season, untouched by IST knockouts.
- The 4 teams eliminated in the IST quarterfinals (round of 8) each have
  1 excluded game (the quarterfinal itself) -> 81 games.
- The 4 teams that reach the IST semifinals (the Vegas "final four") each
  have 2 excluded games (semifinal + championship-or-3rd-place) -> 80 games.

This gives 30*82 - (4*1 + 4*2) = 2460 - 12 = 2448 total expected games
for a season with an in-season tournament.
"""

TEAMS_PER_LEAGUE = 30
BASELINE_GAMES_PER_TEAM = 82

IST_QUARTERFINALIST_COUNT = 4   # teams eliminated in the IST round of 8
IST_QUARTERFINALIST_EXCLUDED_GAMES = 1
IST_QUARTERFINALIST_EXPECTED_GAMES = BASELINE_GAMES_PER_TEAM - IST_QUARTERFINALIST_EXCLUDED_GAMES  # 81

IST_SEMIFINALIST_COUNT = 4      # teams that reach the IST semifinals (Vegas final four)
IST_SEMIFINALIST_EXCLUDED_GAMES = 2
IST_SEMIFINALIST_EXPECTED_GAMES = BASELINE_GAMES_PER_TEAM - IST_SEMIFINALIST_EXCLUDED_GAMES  # 80

UNAFFECTED_TEAM_COUNT = TEAMS_PER_LEAGUE - IST_QUARTERFINALIST_COUNT - IST_SEMIFINALIST_COUNT  # 22

TOTAL_EXPECTED_GAMES = (
    UNAFFECTED_TEAM_COUNT * BASELINE_GAMES_PER_TEAM
    + IST_QUARTERFINALIST_COUNT * IST_QUARTERFINALIST_EXPECTED_GAMES
    + IST_SEMIFINALIST_COUNT * IST_SEMIFINALIST_EXPECTED_GAMES
)  # 2448

# Expected per-team game count -> how many teams should land on that count.
# Note: this only checks *counts*, not which specific teams they belong to.
# A future refinement could hardcode the actual 8 franchises that reached
# the IST knockout round for a given season, for a tighter check.
EXPECTED_GAME_COUNT_DISTRIBUTION = {
    BASELINE_GAMES_PER_TEAM: UNAFFECTED_TEAM_COUNT,
    IST_QUARTERFINALIST_EXPECTED_GAMES: IST_QUARTERFINALIST_COUNT,
    IST_SEMIFINALIST_EXPECTED_GAMES: IST_SEMIFINALIST_COUNT,
}
