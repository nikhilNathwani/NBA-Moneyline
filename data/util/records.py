"""
The pipeline's two game records - one per shape of the production data:

- TeamGame: one team's side of a game, as the scraper produces it (two per
  game) - the shape of the database's team_games view.
- GameRecord: one real game, as transform/build_game_records.py builds it by
  pairing two TeamGames with the official schedule - the shape of the games
  table, and what load/postgres.py inserts.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class TeamGame:
    """One team's side of a game."""
    team: str
    opponent: str
    outcome: bool                       # True if `team` won
    win_odds: int                       # American odds on `team` winning
    lose_odds: int                      # odds on `team` losing (= the opponent's win_odds)
    season_start_year: int              # 2025 = the 2025-26 season
    game_number: Optional[int] = None   # the team's Nth game, by OddsPortal's date (set after scraping)
    listed_date: Optional[date] = None  # OddsPortal's date (its timezone: can be a day after the US date)


@dataclass
class GameRecord:
    """One real game, ready for the production games table."""
    game_date: date                     # from the official schedule
    home: str
    away: str
    neutral_site: bool                  # e.g. played abroad; home/away is then alphabetical, for structure only
    home_won: bool
    home_odds: int                      # American odds on the home team winning
    away_odds: int                      # American odds on the away team winning
