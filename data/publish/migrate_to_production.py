"""
Publishes verified games to the production database (Postgres) that the
web app reads from - migrates them over (Step 3) and verifies the
migration (Steps 5-6).
"""

import os
import psycopg2
from dotenv import load_dotenv
from typing import Dict, List

from util.game import Game


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


def migrate_season_to_postgres(team_games: Dict[str, List[Game]], season: int) -> int:
    """
    Migrate a season's scraped games to Postgres.

    Args:
        team_games: scraped games straight from the scraper's output
        season: Season start year to migrate

    Returns:
        Number of games inserted
    """
    pg_conn = get_postgres_connection()
    pg_cursor = pg_conn.cursor()

    # Delete existing data for this season
    pg_cursor.execute("DELETE FROM games WHERE seasonstartyear = %s", (season,))
    print(f"  Deleted existing data for {season}-{(season+1)%100:02d} season")

    # Insert new data
    inserted = 0
    for team, games in sorted(team_games.items()):
        for game in games:
            # Format odds as strings with +/- prefix
            win_odds_str = f"+{game.winOdds}" if game.winOdds > 0 else str(game.winOdds)
            lose_odds_str = f"+{game.loseOdds}" if game.loseOdds > 0 else str(game.loseOdds)

            try:
                pg_cursor.execute("""
                    INSERT INTO games (team, seasonstartyear, gamenumber, outcome, winodds, loseodds)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (team, season, game.gameNumber, game.outcome, win_odds_str, lose_odds_str))
                inserted += 1
            except Exception as e:
                print(f"  ⚠️  Error inserting game: {team} game {game.gameNumber}: {e}")
                pg_conn.rollback()
                continue

    pg_conn.commit()
    pg_conn.close()

    return inserted
