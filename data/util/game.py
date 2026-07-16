"""
Game object for NBA Moneyline scraper.

Represents a single NBA game from one team's perspective, including outcome and moneyline odds.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Game:
    """Represents an NBA game from one team's perspective."""

    team: str
    opponent: str
    outcome: bool  # True if team won, False if lost
    winOdds: int  # Moneyline odds for this team winning
    loseOdds: int  # Moneyline odds for this team losing (opponent's winOdds)
    seasonStartYear: int  # Calendar year in which the season started
    gameNumber: Optional[int] = None  # Number of game within the season (optional, set during post-processing)

    def __str__(self):
        return (f"Season: {self.seasonStartYear}-{(self.seasonStartYear + 1) % 100:02d}, "
                f"Team: {self.team}, Opponent: {self.opponent}, "
                f"Outcome: {'W' if self.outcome else 'L'}, "
                f"WinOdds: {self.winOdds}, LoseOdds: {self.loseOdds}, "
                f"GameNumber: {self.gameNumber}")
