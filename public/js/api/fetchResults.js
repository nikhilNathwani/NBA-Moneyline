async function fetchResultSummary({
	seasonStartYear,
	team,
	prediction,
	wager,
}) {
	return fetchData(
		"/api/result-summary",
		seasonStartYear,
		team,
		prediction,
		wager,
	);
}

async function fetchTopBets({ seasonStartYear, team, prediction, wager }) {
	return fetchData("/api/top-bets", seasonStartYear, team, prediction, wager);
}

//HELPER FUNCTION
async function fetchData(route, seasonStartYear, team, prediction, wager) {
	const response = await fetch(route, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ seasonStartYear, team, prediction, wager }),
	});
	const json = await response.json(); //json is {message:"success", data:[array of games]}
	return json.data;
}
