const fs = require("fs");
const path = require("path");

// Read SQL query files
const resultSummaryQuery = fs.readFileSync(
	path.join(__dirname, "../queries", "resultSummary.sql"),
	"utf8",
);

const topBetsQuery = fs.readFileSync(
	path.join(__dirname, "../queries", "topBets.sql"),
	"utf8",
);

module.exports = { resultSummaryQuery, topBetsQuery };
