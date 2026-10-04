function formatCentsToDollars(cents, includePlusSign = false) {
	// Determine if amount has cents when converted to dollars
	let hasCents = cents % 100 !== 0;
	let options = {
		style: "currency",
		currency: "USD",
		minimumFractionDigits: hasCents ? 2 : 0,
		maximumFractionDigits: hasCents ? 2 : 0,
	};

	let formatter = new Intl.NumberFormat("en-US", options);
	const amount = formatter.format(cents / 100);
	if (includePlusSign && cents > 0) {
		return "+" + amount;
	}
	return amount;
}

// Moneyline odds with an explicit sign, e.g. 150 -> "+150", -200 -> "-200"
function formatOdds(odds) {
	return `${odds > 0 ? "+" : ""}${odds}`;
}

function formatPercent(number, includePlusSign = true) {
	return `${number >= 0 ? "+" : ""}${number.toPrecision(3)}%`;

	// *The below version converts 0.805 to 0.81 instead of keeping 0.805
	// return `${number >= 0 ? "+" : ""}${Number(
	// 	Number(number.toPrecision(3)).toFixed(2)
	// )}%`;
}
