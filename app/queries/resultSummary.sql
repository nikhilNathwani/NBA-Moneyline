-- Result Summary Query: 
--      Analyzes betting outcomes with profit/loss calculations
-- Parameters:
--      $1 = seasonStartYear
--      $2 = team
--      $3 = prediction (boolean)
--      $4 = wager
--
-- Sample Output:
--      team | seasonStartYear | outcome | is_favorite | wager | num_games | total_profit_cents
--      -----|-----------------|---------|-------------|-------|-----------|--------------------
--      LAL  |      2023       |  true   |    true     |  100  |    42     |       1850
--      LAL  |      2023       |  true   |    false    |  100  |    12     |       2400
--      LAL  |      2023       |  false  |    true     |  100  |    18     |      -1800
--      LAL  |      2023       |  false  |    false    |  100  |    10     |      -1000

WITH integer_odds AS (
	SELECT 
		team,
		seasonStartYear,
		outcome,
		CAST($3 AS boolean) as prediction,
		CAST($4 AS NUMERIC) AS wager,
		CAST(winOdds AS INTEGER) AS winOdds_int,
		CAST(loseOdds AS INTEGER) AS loseOdds_int
		FROM games
		WHERE seasonStartYear = CAST($1 AS integer)
			AND team = CAST($2 AS text)
),
label_favorites AS (
	SELECT 
		*,
		CASE 
			WHEN winOdds_int < 0 THEN TRUE
			ELSE FALSE
			END AS is_favorite
		FROM integer_odds
),
odds_of_prediction AS (
	SELECT 
		team,
		seasonStartYear,
		outcome,
		is_favorite,
		prediction,
		wager,
		CASE 
			WHEN prediction = TRUE THEN winOdds_int
			ELSE loseOdds_int
		END AS odds
		FROM label_favorites
),
profit_per_game AS (
	SELECT 
		team,
		seasonStartYear,
		outcome, 
		is_favorite,
		odds,
		wager,
		FLOOR(
			CASE
			-- Incorrect bet
				WHEN outcome <> prediction THEN -1 * wager
			-- Correct bet, positive odds
				WHEN odds > 0 THEN (wager / 100) * odds
			-- Correct bet, negative odds
				ELSE (wager / (odds * -1)) * 100
			END
		) AS profit_cents
	FROM odds_of_prediction
)
SELECT
	team,
	seasonStartYear,
	outcome, 
	is_favorite,
	CAST(wager AS integer) AS wager,
	CAST(COUNT(*) AS integer) AS num_games,
	CAST(SUM(profit_cents) AS integer) AS total_profit_cents
FROM profit_per_game
GROUP BY team, seasonStartYear, outcome, is_favorite, wager;