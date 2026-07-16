"""
Publishes verified games to the production database (Postgres) that the
web app reads from - migrates them over (Step 3) and verifies the
migration (Steps 5-6). For the staging side, see scrape/save_scraped_data.py.
"""

import os
import sqlite3
import psycopg2
from dotenv import load_dotenv
from typing import Dict, Tuple


def get_postgres_connection():
    """Get connection to Vercel Postgres database."""
    # From data/publish/migrate_to_production.py, go up 2 levels to project root
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        '.env.development.local'
    )
    load_dotenv(env_path)
    return psycopg2.connect(os.getenv('POSTGRES_URL'))


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
