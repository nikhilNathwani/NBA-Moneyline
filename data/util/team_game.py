"""
One team's side of a game, as the scraper produces it - two per game, the
same shape as the database's team_games view (team, opponent, outcome, its
odds). transform/build_game_records.py turns pairs of these into one
GameRecord per real game, the shape of the games table.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class TeamGame:
    """One team's side of a game."""

    team: str
    opponent: str
    outcome: bool  # True if team won, False if lost
    win_odds: int  # Moneyline odds for this team winning
    lose_odds: int  # Moneyline odds for this team losing (opponent's win_odds)
    season_start_year: int  # Calendar year in which the season started
    game_number: Optional[int] = None  # the team's Nth game of the season, by OddsPortal's date (set after scraping)
    listed_date: Optional[date] = None  # the date OddsPortal lists it under (its timezone; can be a day after the US date)

    def __str__(self):
        return (f"Season: {self.season_start_year}-{(self.season_start_year + 1) % 100:02d}, "
                f"Team: {self.team}, Opponent: {self.opponent}, "
                f"Outcome: {'W' if self.outcome else 'L'}, "
                f"Win odds: {self.win_odds}, Lose odds: {self.lose_odds}, "
                f"Game number: {self.game_number}")
