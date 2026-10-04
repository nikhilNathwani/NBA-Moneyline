-- The production `games` table (Vercel Postgres): written by the pipeline
-- (publish/migrate_to_production.py), read by the web app (app/queries/)
-- and the Tableau export (publish/export_tableau_csv.py).
--
-- One row per team per game, so every game appears twice - once from each
-- team's side (the winner's row has outcome = true, the loser's false).
--
-- The constraints are a backstop behind the pipeline's own checks: bad data
-- is rejected by the database itself, whatever wrote it. migrate_to_production
-- also runs whole-season checks (30 teams, wins = losses, game numbers 1..N
-- with no gaps) inside its transaction, since those span many rows.
--
-- The rollback test (tests/publish/test_migration.py) builds its table from
-- this file, so keep it in sync with production.
--
-- History:
--   2026-10-04  Added the primary key, NOT NULLs and CHECKs; changed winodds/
--               loseodds from VARCHAR ("+150") to INTEGER (150). Before this
--               the table had no constraints at all.

CREATE TABLE games (
    team            varchar NOT NULL,
    seasonstartyear integer NOT NULL,  -- calendar year the season started (2025 = 2025-26)
    gamenumber      integer NOT NULL,  -- the team's Nth game of that season, in date order
    outcome         boolean NOT NULL,  -- true if `team` won
    winodds         integer NOT NULL,  -- American moneyline odds on `team` winning
    loseodds        integer NOT NULL,  -- odds on `team` losing (= the opponent's winodds)

    CONSTRAINT games_pkey PRIMARY KEY (team, seasonstartyear, gamenumber),
    CONSTRAINT games_gamenumber_range CHECK (gamenumber BETWEEN 1 AND 82),
    -- American odds are never between -100 and +100
    CONSTRAINT games_winodds_american CHECK (winodds <= -100 OR winodds >= 100),
    CONSTRAINT games_loseodds_american CHECK (loseodds <= -100 OR loseodds >= 100)
);
