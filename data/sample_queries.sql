-- NBA Moneyline Database Queries
-- Handy queries for inspecting the production Vercel Postgres database by hand,
-- e.g. with the VS Code SQLTools extension. Not used by the pipeline or the app.
--
-- Tables (see data/README.md, "The database"):
--   teams       one row per franchise (team_id, name)
--   games       one row per real game (date, home/away team ids, odds, winner)
--   team_games  view: each game from both teams' sides (team, gamenumber,
--               outcome, winodds, loseodds, opponent, game_date, is_home)

-- ============================================================================
-- QUICK CHECKS
-- ============================================================================

SELECT * FROM team_games
LIMIT 10;

-- Show all seasons: games, and teams that played
SELECT
    seasonstartyear,
    CONCAT(seasonstartyear, '-', LPAD(((seasonstartyear + 1) % 100)::TEXT, 2, '0')) AS season,
    COUNT(*) AS games,
    (SELECT COUNT(DISTINCT team) FROM team_games t WHERE t.seasonstartyear = g.seasonstartyear) AS teams
FROM games g
GROUP BY seasonstartyear
ORDER BY seasonstartyear;

-- Show total games in database
SELECT COUNT(*) AS total_games FROM games;

-- ============================================================================
-- DATABASE STRUCTURE
-- ============================================================================

-- Show each table's columns
SELECT
    table_name,
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_name IN ('teams', 'games', 'team_games')
ORDER BY table_name, ordinal_position;

-- Show constraints (keys and value rules)
SELECT
    conrelid::regclass AS table_name,
    conname,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN ('teams'::regclass, 'games'::regclass)
ORDER BY 1, 2;

-- Show the team_games view's definition
SELECT pg_get_viewdef('team_games', true);

-- ============================================================================
-- DATA VALIDATION
-- ============================================================================

-- Games per team for a specific season
SELECT
    team,
    COUNT(*) AS game_count
FROM team_games
WHERE seasonstartyear = 2024  -- Change to season you want to check
GROUP BY team
ORDER BY game_count DESC, team;

-- Teams with something other than 82 games (expected in some seasons -
-- see data/util/constants.py)
SELECT
    seasonstartyear,
    team,
    COUNT(*) AS game_count
FROM team_games
GROUP BY seasonstartyear, team
HAVING COUNT(*) != 82
ORDER BY seasonstartyear, team;

-- Home win rate per season (usually 54-60%)
SELECT
    seasonstartyear,
    ROUND(100.0 * AVG(home_won::int), 1) AS home_win_pct
FROM games
WHERE NOT neutral_site
GROUP BY seasonstartyear
ORDER BY seasonstartyear;

-- Neutral-site games (home/away is alphabetical for these)
SELECT g.game_date, h.name AS home, a.name AS away, g.home_won
FROM games g
JOIN teams h ON h.team_id = g.home_team_id
JOIN teams a ON a.team_id = g.away_team_id
WHERE g.neutral_site
ORDER BY g.game_date;

-- ============================================================================
-- SAMPLE DATA
-- ============================================================================

-- Get 10 random games from most recent season
SELECT
    team,
    gamenumber,
    game_date,
    opponent,
    outcome,
    winodds,
    loseodds
FROM team_games
WHERE seasonstartyear = (SELECT MAX(seasonstartyear) FROM games)
ORDER BY RANDOM()
LIMIT 10;

-- Get a full season for one team
SELECT
    gamenumber,
    game_date,
    opponent,
    is_home,
    outcome,
    winodds,
    loseodds
FROM team_games
WHERE team = 'Boston Celtics'
  AND seasonstartyear = 2024
ORDER BY gamenumber;

-- One team's record against each opponent in a season
SELECT
    opponent,
    SUM(CASE WHEN outcome THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN NOT outcome THEN 1 ELSE 0 END) AS losses
FROM team_games
WHERE team = 'Boston Celtics'
  AND seasonstartyear = 2024
GROUP BY opponent
ORDER BY wins DESC, opponent;

-- ============================================================================
-- SEASON SUMMARIES
-- ============================================================================

-- Win/loss record for all teams in a season
SELECT
    team,
    SUM(CASE WHEN outcome THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN NOT outcome THEN 1 ELSE 0 END) AS losses,
    COUNT(*) AS total_games
FROM team_games
WHERE seasonstartyear = 2024
GROUP BY team
ORDER BY wins DESC;

-- How often favorites win, by how heavily they were favored
SELECT
    CASE
        WHEN winodds >= -199 THEN '1. Slight favorite (-100 to -199)'
        WHEN winodds >= -299 THEN '2. Favorite (-200 to -299)'
        WHEN winodds >= -499 THEN '3. Strong favorite (-300 to -499)'
        ELSE '4. Heavy favorite (-500 or more)'
    END AS favorite_range,
    COUNT(*) AS games,
    ROUND(100.0 * AVG(outcome::int), 1) AS win_pct
FROM team_games
WHERE winodds < 0
GROUP BY favorite_range
ORDER BY favorite_range;

-- ============================================================================
-- AFTER MIGRATION CHECKS
-- ============================================================================

-- Verify a new season was added successfully
SELECT
    seasonstartyear,
    COUNT(*) AS games,
    MIN(game_date) AS first_game,
    MAX(game_date) AS last_game
FROM games
WHERE seasonstartyear = 2025  -- Change to season you just migrated
GROUP BY seasonstartyear;

-- Compare game counts across all seasons
SELECT
    seasonstartyear,
    COUNT(*) AS games,
    COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY seasonstartyear) AS diff_from_prev
FROM games
GROUP BY seasonstartyear
ORDER BY seasonstartyear;

-- ============================================================================
-- CLEANUP / MAINTENANCE
-- ============================================================================

-- Delete a season (if migration had issues) - re-running the pipeline for
-- that season does this anyway
-- DELETE FROM games WHERE seasonstartyear = 2025;

-- Get database size
SELECT
    pg_size_pretty(pg_database_size(current_database())) AS database_size;

-- Get table sizes
SELECT
    pg_size_pretty(pg_total_relation_size('games')) AS games_size,
    pg_size_pretty(pg_total_relation_size('teams')) AS teams_size;
