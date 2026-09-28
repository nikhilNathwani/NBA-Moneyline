/* External imports */
const express = require("express");
const path = require("path");

/* Internal imports */
const resultSummaryRoute = require("./app/routes/resultSummary");
const topBetsRoute = require("./app/routes/topBets");

/* App Configuration */
const app = express();

// Middleware to parse request bodies (for POST requests)
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Use the routes I defined
app.use("/api/result-summary", resultSummaryRoute);
app.use("/api/top-bets", topBetsRoute);

// Serve static files from public folder
const staticPathRoot = path.join(__dirname, "public");
app.use(express.static(staticPathRoot));

// Fallback to serve index.html for any other route
app.get("/{*splat}", (req, res) => {
	res.sendFile(path.join(staticPathRoot, "index.html"));
});

module.exports = app;
