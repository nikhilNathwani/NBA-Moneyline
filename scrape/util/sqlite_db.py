"""
SQLite utilities for the NBA Moneyline data pipeline.

Handles saving scraped game data to SQLite (Step 1) and verifying it
before migration to Postgres (Step 2). For Postgres-side storage, see
util/postgres_db.py.
"""

import sqlite3
import os
from collections import Counter
from typing import Dict, List
from util.game import Game
from util.constants import TOTAL_EXPECTED_GAMES, EXPECTED_GAME_COUNT_DISTRIBUTION


def save_to_database(all_games: Dict[int, Dict[str, List[Game]]], db_path: str):
    """
    Save scraped games to SQLite database.
    
    Creates a table 'games' with the following schema:
    - team (TEXT)
    - seasonStartYear (INTEGER)
    - gameNumber (INTEGER)
    - outcome (INTEGER): 1 for win, 0 for loss
    - winOdds (INTEGER)
    - loseOdds (INTEGER)
    - opponent (TEXT)
    
    Args:
        all_games: Dictionary mapping season start years to team games
        db_path: Path to save SQLite database
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table (drop if exists)
    cursor.execute('DROP TABLE IF EXISTS games')
    cursor.execute('''
        CREATE TABLE games (
            team TEXT NOT NULL,
            seasonStartYear INTEGER NOT NULL,
            gameNumber INTEGER NOT NULL,
            outcome INTEGER NOT NULL,
            winOdds INTEGER NOT NULL,
            loseOdds INTEGER NOT NULL,
            opponent TEXT NOT NULL,
            PRIMARY KEY (team, seasonStartYear, gameNumber)
        )
    ''')
    
    # Insert all games
    game_count = 0
    for season, teams in all_games.items():
        for team, games in teams.items():
            for game in games:
                cursor.execute('''
                    INSERT INTO games 
                    (team, seasonStartYear, gameNumber, outcome, winOdds, loseOdds, opponent)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game.team,
                    game.seasonStartYear,
                    game.gameNumber,
                    1 if game.outcome else 0,  # Convert boolean to int
                    game.winOdds,
                    game.loseOdds,
                    game.opponent
                ))
                game_count += 1
    
    # Create indexes for common queries
    cursor.execute('CREATE INDEX idx_team ON games(team)')
    cursor.execute('CREATE INDEX idx_season ON games(seasonStartYear)')
    cursor.execute('CREATE INDEX idx_team_season ON games(team, seasonStartYear)')
    
    # Commit and close
    conn.commit()
    conn.close()
    
    print(f"Saved {game_count} games to database with indexes")


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
