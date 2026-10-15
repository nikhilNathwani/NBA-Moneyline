// State var to track if this is the first submit
let isAwaitingFirstSubmit = true;
//
const submitButton = document.getElementById("submit-button");

// Handle submit ('View Results' button)
submitButton.addEventListener("click", handleSubmit);

async function handleSubmit() {
	// Step 1: Start fetching immediately
	const filterValues = getFilterValues();
	const resultSummaryPromise = fetchResultSummary(filterValues);
	const topBetsPromise = fetchTopBets(filterValues);

	// Step 2: Start collapsing UI and measuring delay
	const uiTransitionPromise = isAwaitingFirstSubmit
		? unhideResultsUI(isAwaitingFirstSubmit, isWideScreen())
		: resetResultsUI(isAwaitingFirstSubmit, isWideScreen());

	// Step 3: Wait for data + timeout in parallel
	try {
		const [resultSummary, topBets, _] = await Promise.all([
			resultSummaryPromise,
			topBetsPromise,
			uiTransitionPromise,
		]);

		// Step 4: Populate result elements
		populateResultSummary(
			resultSummary,
			filterValues.prediction,
			filterValues.wager,
		);
		populateTopBets(topBets, filterValues.prediction, filterValues.wager);

		// Step 5: Fade in new results
		// fadeInResults();
		setTimeout(fadeInResults, 600);

		// Step 6: Update state var (no longer awaiting first submit)
		isAwaitingFirstSubmit = false;
	} catch (err) {
		console.error("Error fetching results:", err);
	}
}
