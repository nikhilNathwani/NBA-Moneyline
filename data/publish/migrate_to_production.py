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
from util.paths import PROJECT_ROOT


def get_postgres_connection():
    """Get connection to Vercel Postgres database."""
    env_path = os.path.join(PROJECT_ROOT, '.env.development.local')
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


def _formatOdds(odds: int) -> str:
    """Format moneyline odds as a string with an explicit +/- prefix."""
    return f"+{odds}" if odds > 0 else str(odds)


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
            win_odds_str = _formatOdds(game.winOdds)
            lose_odds_str = _formatOdds(game.loseOdds)

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
