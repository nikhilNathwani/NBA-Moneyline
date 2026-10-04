"""
Publishes verified games to the production database (Postgres) that the
web app reads from - migrates them over (Step 3) and verifies the
migration (Steps 5-6).
"""

import os
import psycopg2
from psycopg2.extras import execute_values
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


# Whole-season checks run inside the migration transaction, after the
# inserts: each query returns a count of problems (0 = pass). These span many
# rows, so they can't be table constraints like the per-row rules in schema.sql.
SEASON_CHECKS = {
    "the season doesn't have exactly 30 teams": """
        SELECT ABS(COUNT(DISTINCT team) - 30) FROM games WHERE seasonstartyear = %(season)s
    """,
    # Every game has one winner row and one loser row
    "wins don't equal losses": """
        SELECT ABS(COUNT(*) FILTER (WHERE outcome) - COUNT(*) FILTER (WHERE NOT outcome))
        FROM games WHERE seasonstartyear = %(season)s
    """,
    # With the primary key ruling out repeats, max = count means exactly 1..N
    "some team's game numbers aren't 1..N with no gaps": """
        SELECT COUNT(*) FROM (
            SELECT team FROM games WHERE seasonstartyear = %(season)s
            GROUP BY team HAVING MIN(gamenumber) <> 1 OR MAX(gamenumber) <> COUNT(*)
        ) gaps
    """,
}


def _check_season(cursor, season: int):
    """Raise (rolling back the migration) if any whole-season check fails."""
    failures = []
    for description, query in SEASON_CHECKS.items():
        cursor.execute(query, {"season": season})
        if cursor.fetchone()[0] != 0:
            failures.append(description)
    if failures:
        raise ValueError(f"season checks failed: {'; '.join(failures)}")


def migrate_season_to_postgres(team_games: Dict[str, List[Game]], season: int) -> int:
    """
    Migrate a season's scraped games to Postgres.

    Args:
        team_games: scraped games straight from the scraper's output
        season: Season start year to migrate

    All-or-nothing: the delete, every insert and the whole-season checks run
    in one transaction, so any error or failed check rolls the whole season
    back and leaves production exactly as it was (never the old season plus
    part of the new one). The table's own constraints (schema.sql) reject
    bad individual rows the same way.

    Returns:
        Number of team-game rows inserted (2 per game)
    """
    rows = [
        (team, season, game.gameNumber, game.outcome, game.winOdds, game.loseOdds)
        for team, games in sorted(team_games.items())
        for game in games
    ]

    pg_conn = get_postgres_connection()
    try:
        # `with pg_conn` commits on success and rolls back on any exception
        # (it doesn't close the connection - the finally below does that).
        with pg_conn, pg_conn.cursor() as pg_cursor:
            pg_cursor.execute("DELETE FROM games WHERE seasonstartyear = %s", (season,))
            print(f"  Deleting {pg_cursor.rowcount} existing rows for {season}-{(season+1)%100:02d} season")

            execute_values(pg_cursor, """
                INSERT INTO games (team, seasonstartyear, gamenumber, outcome, winodds, loseodds)
                VALUES %s
            """, rows)

            _check_season(pg_cursor, season)
    finally:
        pg_conn.close()

    return len(rows)
