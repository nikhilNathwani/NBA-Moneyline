"""
Data export utilities for NBA Moneyline scraper.

Handles saving scraped game data to SQLite.
"""

import sqlite3
import os
from typing import Dict, List
from util.game import Game


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
