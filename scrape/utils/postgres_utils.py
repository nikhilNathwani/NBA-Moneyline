"""
PostgreSQL database utilities for NBA Moneyline data pipeline.

Handles migration from SQLite to Postgres and database verification.
"""

import os
import sqlite3
import psycopg2
from collections import Counter
from dotenv import load_dotenv
from typing import Dict, Tuple

from utils.constants import TOTAL_EXPECTED_GAMES, EXPECTED_GAME_COUNT_DISTRIBUTION


def get_postgres_connection():
    """Get connection to Vercel Postgres database."""
    # From scrape/utils/postgres_utils.py, go up 2 levels to project root
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        '.env.development.local'
    )
    load_dotenv(env_path)
    return psycopg2.connect(os.getenv('POSTGRES_URL'))


def verify_scraped_data(db_path: str, season: int) -> Dict:
    """
    Verify scraped data in SQLite database.

    Returns dict with:
        - total_games: int
        - team_counts: list of (team, count) tuples
        - total_games_ok: bool (matches TOTAL_EXPECTED_GAMES)
        - distribution_ok: bool (per-team counts match the expected
          82/81/80 distribution accounting for the in-season tournament,
          see utils/constants.py)
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


def verify_postgres_migration() -> Dict:
    """
    Verify data in Postgres database.
    
    Returns dict with:
        - season_counts: list of (season, count) tuples
        - error: str (if connection failed)
    """
    try:
        conn = get_postgres_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT seasonstartyear, COUNT(*) as game_count
            FROM games
            GROUP BY seasonstartyear
            ORDER BY seasonstartyear
        """)
        season_counts = cursor.fetchall()
        
        conn.close()
        
        return {'season_counts': season_counts}
    except Exception as e:
        return {'error': str(e)}


def migrate_season_to_postgres(db_path: str, season: int) -> int:
    """
    Migrate a season from SQLite to Postgres.
    
    Args:
        db_path: Path to SQLite database
        season: Season start year to migrate
        
    Returns:
        Number of games inserted
    """
    # Get SQLite data
    sqlite_conn = sqlite3.connect(db_path)
    cursor = sqlite_conn.cursor()
    
    cursor.execute("""
        SELECT team, seasonStartYear, gameNumber, outcome, winOdds, loseOdds
        FROM games
        WHERE seasonStartYear = ?
        ORDER BY team, gameNumber
    """, (season,))
    
    games = cursor.fetchall()
    sqlite_conn.close()
    
    # Get Postgres connection
    pg_conn = get_postgres_connection()
    pg_cursor = pg_conn.cursor()
    
    # Delete existing data for this season
    pg_cursor.execute("DELETE FROM games WHERE seasonstartyear = %s", (season,))
    print(f"  Deleted existing data for {season}-{(season+1)%100:02d} season")
    
    # Insert new data
    inserted = 0
    for game in games:
        team, season_year, game_num, outcome, win_odds, lose_odds = game
        
        # Convert outcome to boolean
        outcome_bool = bool(outcome)
        
        # Format odds as strings with +/- prefix
        win_odds_int = int(win_odds)
        lose_odds_int = int(lose_odds)
        win_odds_str = f"+{win_odds_int}" if win_odds_int > 0 else str(win_odds_int)
        lose_odds_str = f"+{lose_odds_int}" if lose_odds_int > 0 else str(lose_odds_int)
        
        try:
            pg_cursor.execute("""
                INSERT INTO games (team, seasonstartyear, gamenumber, outcome, winodds, loseodds)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (team, season_year, game_num, outcome_bool, win_odds_str, lose_odds_str))
            inserted += 1
        except Exception as e:
            print(f"  ⚠️  Error inserting game: {team} game {game_num}: {e}")
            pg_conn.rollback()
            continue
    
    pg_conn.commit()
    pg_conn.close()
    
    return inserted
