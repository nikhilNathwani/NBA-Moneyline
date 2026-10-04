// Section 4: Top Three Bets
function populateTopBets(topThreeBets, prediction, wager) {
	const topBetsSection = document.getElementById("top-bets-result");
	const topBets = topBetsSection.querySelectorAll(".result-chip");

	topBets.forEach((topBet, index) => {
		//
		// 1) Top Bet Header:
		//
		// E.g.:
		//
		//   Game #24   <-- gameNumberDiv
		//   +$310.56   <-- profitDiv
		//
		const gameNumberDiv = topBet.querySelector(".result-chip-title");
		populateResultElement({
			element: gameNumberDiv,
			value: `Game #${topThreeBets[index].game_number}`,
			textFormatFn: null,
			applySignAndColor: false,
		});
		const profitDiv = topBet.querySelector(".result-chip-value");
		populateResultElement({
			element: profitDiv,
			value: topThreeBets[index].profit_cents,
			textFormatFn: formatCentsToDollars,
			applySignAndColor: true,
		});

		//
		// 2) Top Bet Table:
		// E.g.:
		//  ____________________________________
		//  | Outcome             | [Win/Loss] |  <-- Row I)
		//  | Odds to [Win/Lose]  | +480       |  <-- Row II)
		//  | Wager               | $50        |  <-- Row III)
		//  | Payout              | $290       |  <-- Row IV)
		//  ____________________________________
		const gameTable = topBet.querySelector("table");

		// Row I) Outcome
		const gameTableOutcome = gameTable.querySelector(
			"tr.result-chip-table-outcome"
		);
		populateResultElement({
			element: gameTableOutcome.querySelector("td"),
			value: prediction ? "Win" : "Loss",
			textFormatFn: null,
			applySignAndColor: false,
		});

		// Row II) Odds
		const gameTableOdds = gameTable.querySelector(
			"tr.result-chip-table-odds"
		);
		gameTableOdds.querySelector("th").textContent = prediction
			? "Odds to Win"
			: "Odds to Lose";
		populateResultElement({
			element: gameTableOdds.querySelector("td"),
			value: topThreeBets[index].odds,
			textFormatFn: formatOdds,
			applySignAndColor: false,
		});

		// Row III) Wager
		const gameTableWager = gameTable.querySelector(
			"tr.result-chip-table-wager"
		);
		populateResultElement({
			element: gameTableWager.querySelector("td"),
			value: wager,
			textFormatFn: formatCentsToDollars,
			applySignAndColor: false,
		});

		// Row IV) Payout
		const gameTablePayout = gameTable.querySelector(
			"tr.result-chip-table-payout"
		);
		populateResultElement({
			element: gameTablePayout.querySelector("td"),
			value: wager + topThreeBets[index].profit_cents,
			textFormatFn: formatCentsToDollars,
			applySignAndColor: false,
		});
	});
}
