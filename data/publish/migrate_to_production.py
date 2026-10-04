"""
Publishes verified games to the production database (Postgres) that the
web app reads from - migrates them over (Step 3) and verifies the
migration (Step 5).

Writes one row per real game to the `games` table; the web app and the
Tableau export read the `team_games` view, which presents each game from
both teams' sides. See data/README.md, "The database".
"""

import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from typing import Dict, List

from validate.matching import GameRecord
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
        - season_counts: list of (season, number of games) tuples
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
# rows, so they can't be table constraints like the per-row rules on games.
SEASON_CHECKS = {
    "the season doesn't have exactly 30 teams": """
        SELECT ABS(COUNT(DISTINCT team) - 30) FROM team_games WHERE seasonstartyear = %(season)s
    """,
    # The table's UNIQUE constraints stop a team being home twice (or away
    # twice) on one date; this catches home in one game and away in another
    "some team plays twice on the same date": """
        SELECT COUNT(*) FROM (
            SELECT team FROM team_games WHERE seasonstartyear = %(season)s
            GROUP BY team, game_date HAVING COUNT(*) > 1
        ) doubled
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


def migrate_season_to_postgres(records: List[GameRecord], season: int) -> int:
    """
    Migrate a season's games (from validate.matching) to Postgres.

    Args:
        records: one GameRecord per real game
        season: Season start year to migrate

    All-or-nothing: the delete, every insert and the whole-season checks run
    in one transaction, so any error or failed check rolls the whole season
    back and leaves production exactly as it was (never the old season plus
    part of the new one). The tables' own constraints reject bad individual
    rows the same way - including any team name not in the teams table.

    Returns:
        Number of games inserted
    """
    pg_conn = get_postgres_connection()
    try:
        # `with pg_conn` commits on success and rolls back on any exception
        # (it doesn't close the connection - the finally below does that).
        with pg_conn, pg_conn.cursor() as pg_cursor:
            pg_cursor.execute("SELECT name, team_id FROM teams")
            team_ids = dict(pg_cursor.fetchall())
            unknown = sorted({t for r in records for t in (r.home, r.away)} - team_ids.keys())
            if unknown:
                raise ValueError(f"teams not in the teams table: {', '.join(unknown)}")

            pg_cursor.execute("DELETE FROM games WHERE seasonstartyear = %s", (season,))
            print(f"  Deleting {pg_cursor.rowcount} existing games for {season}-{(season+1)%100:02d} season")

            execute_values(pg_cursor, """
                INSERT INTO games (seasonstartyear, game_date, home_team_id, away_team_id,
                                   neutral_site, home_won, home_odds, away_odds)
                VALUES %s
            """, [(season, r.game_date, team_ids[r.home], team_ids[r.away], r.neutral_site,
                   r.home_won, r.home_odds, r.away_odds) for r in records])

            _check_season(pg_cursor, season)
    finally:
        pg_conn.close()

    return len(records)
