"""
Tests for publish.migrate_to_production against a real, throwaway Postgres
server. Migrations only ever write to that throwaway server; production is
only *read*, once, for the `games` table's current definition (columns and
constraints), so the test table always matches the real one and the real
constraints are exercised too.

The point is the all-or-nothing guarantee - a successful migration replaces
exactly one season, and any failure (a bad row, a duplicate, a failed
whole-season check) leaves the table exactly as it was.

Skipped when no local Postgres install is found (initdb on PATH, or
Postgres.app on macOS), or when production can't be reached (no
POSTGRES_URL in .env.development.local, or no network).
"""

import os
import shutil
import socket
import subprocess
import tempfile

import psycopg2
import pytest

import publish.migrate_to_production as migration
from util.game import Game
from util.paths import PROJECT_ROOT

POSTGRES_APP_BIN = "/Applications/Postgres.app/Contents/Versions/latest/bin"


# Captured before any test points get_postgres_connection at the throwaway server
_connect_to_production = migration.get_postgres_connection


@pytest.fixture(scope="module")
def games_table_ddl():
    """CREATE TABLE for `games`, rebuilt from production's catalog (read-only)."""
    env_path = os.path.join(PROJECT_ROOT, ".env.development.local")
    if not os.path.exists(env_path) and not os.getenv("POSTGRES_URL"):
        pytest.skip("no database credentials - run `npm run sync-env` from the project root "
                    "to pull .env.development.local from Vercel")
    try:
        conn = _connect_to_production()
    except Exception as e:
        pytest.skip(f"can't reach production to read the games table definition "
                    f"({e.__class__.__name__}) - check your network connection and POSTGRES_URL")
    try:
        conn.set_session(readonly=True)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT attname, format_type(atttypid, atttypmod), attnotnull
            FROM pg_attribute
            WHERE attrelid = 'public.games'::regclass AND attnum > 0 AND NOT attisdropped
            ORDER BY attnum
        """)
        columns = [f"{name} {type_}{' NOT NULL' if not_null else ''}"
                   for name, type_, not_null in cursor.fetchall()]
        cursor.execute("""
            SELECT conname, pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'public.games'::regclass
            ORDER BY conname
        """)
        constraints = [f"CONSTRAINT {name} {definition}" for name, definition in cursor.fetchall()]
    finally:
        conn.close()
    return f"CREATE TABLE games ({', '.join(columns + constraints)})"


def _find_postgres_bin():
    initdb = shutil.which("initdb")
    if initdb:
        return os.path.dirname(initdb)
    if os.path.exists(os.path.join(POSTGRES_APP_BIN, "initdb")):
        return POSTGRES_APP_BIN
    return None


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def postgres_dsn():
    """Start a throwaway Postgres server for this module, then delete it."""
    bin_dir = _find_postgres_bin()
    if bin_dir is None:
        pytest.skip("no local Postgres install found")

    data_dir = tempfile.mkdtemp(prefix="moneyline_pg_")
    port = _free_port()
    try:
        subprocess.run([os.path.join(bin_dir, "initdb"), "-D", data_dir, "-U", "test", "-A", "trust"],
                       check=True, capture_output=True)
        # TCP only: a Unix socket path inside a long temp dir can exceed macOS's limit
        subprocess.run([os.path.join(bin_dir, "pg_ctl"), "-D", data_dir, "-w", "-l", os.path.join(data_dir, "log"),
                        "-o", f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories=''",
                        "start"], check=True, capture_output=True)
        yield f"host=127.0.0.1 port={port} user=test dbname=postgres"
    finally:
        subprocess.run([os.path.join(bin_dir, "pg_ctl"), "-D", data_dir, "-m", "immediate", "stop"],
                       capture_output=True)
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture
def db(postgres_dsn, games_table_ddl, monkeypatch):
    """A fresh `games` table matching production's, with migrations pointed at it."""
    conn = psycopg2.connect(postgres_dsn)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS games")
    cursor.execute(games_table_ddl)
    monkeypatch.setattr(migration, "get_postgres_connection", lambda: psycopg2.connect(postgres_dsn))
    yield cursor
    conn.close()


def _season(season, games_per_team=2, num_teams=30):
    """A valid scraped season: teams paired off, each pair playing every game,
    the first team of each pair winning at -150 / +130."""
    team_games = {}
    for i in range(0, num_teams, 2):
        home, away = f"Team {i:02d}", f"Team {i + 1:02d}"
        for n in range(1, games_per_team + 1):
            team_games.setdefault(home, []).append(Game(home, away, True, -150, 130, season, n))
            team_games.setdefault(away, []).append(Game(away, home, False, 130, -150, season, n))
    return team_games


def _table(cursor):
    cursor.execute("SELECT * FROM games ORDER BY seasonstartyear, team, gamenumber")
    return cursor.fetchall()


def test_migration_replaces_only_its_own_season(db):
    migration.migrate_season_to_postgres(_season(2024, games_per_team=3), 2024)
    migration.migrate_season_to_postgres(_season(2025, games_per_team=3), 2025)

    inserted = migration.migrate_season_to_postgres(_season(2025, games_per_team=2), 2025)

    assert inserted == 60
    db.execute("SELECT seasonstartyear, COUNT(*) FROM games GROUP BY 1 ORDER BY 1")
    assert db.fetchall() == [(2024, 90), (2025, 60)]


def test_odds_are_stored_as_integers(db):
    migration.migrate_season_to_postgres(_season(2025, games_per_team=1), 2025)

    db.execute("SELECT winodds, loseodds FROM games WHERE team = 'Team 00'")
    assert db.fetchone() == (-150, 130)


def _assert_failed_migration_changes_nothing(db, bad_season_games):
    migration.migrate_season_to_postgres(_season(2025), 2025)
    before = _table(db)

    with pytest.raises(Exception):
        migration.migrate_season_to_postgres(bad_season_games, 2025)

    assert _table(db) == before


def test_bad_row_rolls_back_everything(db):
    games = _season(2025)
    games["Team 29"][-1].winOdds = 50  # not valid American odds - rejected by a CHECK
    _assert_failed_migration_changes_nothing(db, games)


def test_duplicate_game_rolls_back_everything(db):
    games = _season(2025)
    games["Team 29"][-1].gameNumber = 1  # a second "game 1" - rejected by the primary key
    _assert_failed_migration_changes_nothing(db, games)


def test_missing_team_fails_season_check_and_rolls_back(db):
    games = _season(2025)
    del games["Team 29"]  # 29 teams, and wins no longer equal losses
    _assert_failed_migration_changes_nothing(db, games)


def test_gap_in_game_numbers_fails_season_check_and_rolls_back(db):
    games = _season(2025, games_per_team=3)
    for team_games in games.values():
        team_games[-1].gameNumber = 4  # games 1, 2, 4 - every row valid, the season isn't
    _assert_failed_migration_changes_nothing(db, games)
