"""
Data export utilities for NBA Moneyline scraper.

Handles saving scraped game data to JSON and SQLite database formats.
"""

import json
import sqlite3
import os
from typing import Dict, List
from util.game import Game


def save_to_json(all_games: Dict[int, Dict[str, List[Game]]], output_path: str):
    """
    Save scraped games to JSON file.
    
    Args:
        all_games: Dictionary mapping season start years to team games
                  Format: {2022: {"Lakers": [Game, ...], "Celtics": [...]}, 2023: {...}}
        output_path: Path to save JSON file
    """
    # Convert Game objects to dictionaries
    json_data = {}
    for season, teams in all_games.items():
        json_data[season] = {}
        for team, games in teams.items():
            json_data[season][team] = [game.to_dict() for game in games]
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Write JSON file
    with open(output_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"Saved {sum(len(t) for s in json_data.values() for t in s.values())} games to JSON")


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


def load_from_json(json_path: str) -> Dict[int, Dict[str, List[Game]]]:
    """
    Load games from JSON file.
    
    Args:
        json_path: Path to JSON file
        
    Returns:
        Dict[int, Dict[str, List[Game]]]: Loaded games data
    """
    with open(json_path, 'r') as f:
        json_data = json.load(f)
    
    # Convert dictionaries back to Game objects
    all_games = {}
    for season_str, teams in json_data.items():
        season = int(season_str)
        all_games[season] = {}
        for team, games_data in teams.items():
            all_games[season][team] = [
                Game(**game_dict) for game_dict in games_data
            ]
    
    return all_games


def verify_data(all_games: Dict[int, Dict[str, List[Game]]]) -> bool:
    """
    Verify scraped data for consistency and completeness.
    
    Checks:
    - All teams have games
    - Game numbers are sequential
    - Odds are reasonable
    - Outcomes are boolean
    
    Args:
        all_games: Dictionary of scraped games
        
    Returns:
        bool: True if verification passes, False otherwise
    """
    errors = []
    
    for season, teams in all_games.items():
        for team, games in teams.items():
            if not games:
                errors.append(f"Season {season}, Team {team}: No games found")
                continue
            
            # Check game numbers are sequential
            game_numbers = [g.gameNumber for g in games]
            expected = list(range(1, len(games) + 1))
            if game_numbers != expected:
                errors.append(f"Season {season}, Team {team}: Game numbers not sequential")
            
            # Check each game
            for game in games:
                # Check outcome is boolean
                if not isinstance(game.outcome, bool):
                    errors.append(f"Season {season}, Team {team}, Game {game.gameNumber}: Invalid outcome")
                
                # Check odds are reasonable (between -1000 and +1000, typical range)
                if not (-1000 <= game.winOdds <= 1000):
                    errors.append(f"Season {season}, Team {team}, Game {game.gameNumber}: Suspicious winOdds: {game.winOdds}")
                if not (-1000 <= game.loseOdds <= 1000):
                    errors.append(f"Season {season}, Team {team}, Game {game.gameNumber}: Suspicious loseOdds: {game.loseOdds}")
    
    if errors:
        print("❌ Verification failed with errors:")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  - {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")
        return False
    
    print("✅ Data verification passed!")
    return True
