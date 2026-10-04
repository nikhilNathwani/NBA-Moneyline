-- Top Bets Query: 
--      Finds the top 3 highest-earning bets for given criteria
-- Parameters: 
--      $1 = seasonStartYear
--      $2 = team
--      $3 = prediction (boolean)
--      $4 = wager
--
-- Sample Output:
--      game_number | outcome | odds  | wager | profit_cents
--      ------------|---------|-------|-------|-------------
--         1247     |  true   | +450  |  100  |     450
--         1298     |  true   | +380  |  100  |     380
--         1352     |  true   | +340  |  100  |     340

WITH odds_of_prediction AS (
	SELECT 
		gameNumber AS game_number,
		outcome,
		CAST($4 AS NUMERIC) AS wager,
		CASE 
			WHEN $3 = TRUE THEN winOdds
			ELSE loseOdds
		END AS odds_string 
		FROM games
		WHERE seasonStartYear = $1 
			AND team = $2
			AND outcome = $3
),
odds_as_int AS (
	SELECT 
		game_number, 
		outcome,
		wager,
		odds_string,
		CAST(odds_string AS INTEGER) AS odds_int
	FROM odds_of_prediction
),
top_bets AS (
	SELECT *
	FROM odds_as_int
	ORDER BY odds_int DESC
	LIMIT 3 
)
SELECT
	game_number, 
	outcome, 
	odds_int AS odds,
	CAST(wager AS integer) AS wager,
	CAST(FLOOR(
		CASE 
			WHEN odds_int > 0 THEN (wager / 100) * odds_int
			ELSE (wager/(odds_int * -1)) * 100
		END
	) AS integer) AS profit_cents
FROM top_bets;