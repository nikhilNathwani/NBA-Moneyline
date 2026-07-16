"""
Game object for NBA Moneyline scraper.

Represents a single NBA game from one team's perspective, including outcome and moneyline odds.
"""

class Game:
    """
    Represents an NBA game from one team's perspective.
    
    Attributes:
        team (str): Team name
        opponent (str): Opponent team name
        outcome (bool): True if team won, False if lost
        winOdds (int): Moneyline odds for this team winning
        loseOdds (int): Moneyline odds for this team losing (opponent's winOdds)
        seasonStartYear (int): Calendar year in which the season started
        gameNumber (int): Number of game within the season (1st game is 1, 2nd is 2, etc.)
    """
    
    def __init__(self, team: str, opponent: str, outcome: bool, 
                 winOdds: int, loseOdds: int, seasonStartYear: int, gameNumber: int = None):
        """
        Initialize a Game object.
        
        Args:
            team: Team name
            opponent: Opponent team name
            outcome: True if team won, False if lost
            winOdds: Moneyline odds for this team winning
            loseOdds: Moneyline odds for this team losing
            seasonStartYear: Calendar year in which the season started
            gameNumber: Game number (optional, typically set during post-processing)
        """
        self.team = team
        self.opponent = opponent
        self.outcome = outcome
        self.winOdds = winOdds
        self.loseOdds = loseOdds
        self.seasonStartYear = seasonStartYear
        self.gameNumber = gameNumber

    def __str__(self):
        return (f"Season: {self.seasonStartYear}-{(self.seasonStartYear + 1) % 100:02d}, "
                f"Team: {self.team}, Opponent: {self.opponent}, "
                f"Outcome: {'W' if self.outcome else 'L'}, "
                f"WinOdds: {self.winOdds}, LoseOdds: {self.loseOdds}, "
                f"GameNumber: {self.gameNumber}")
    
    def to_dict(self):
        """Convert game to dictionary for JSON serialization."""
        return {
            "team": self.team,
            "seasonStartYear": self.seasonStartYear,
            "gameNumber": self.gameNumber,
            "outcome": self.outcome,
            "winOdds": self.winOdds,
            "loseOdds": self.loseOdds,
            "opponent": self.opponent
        }