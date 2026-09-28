const express = require("express");
const path = require("path");
const pool = require("./dbConfig");

/**
 * Creates an Express router for a given SQL query.
 * @param {string} query - SQL query text with placeholders ($1, $2, etc.)
 */
function createQueryRoute(query) {
	const router = express.Router();

	router.post("/", async (req, res) => {
		try {
			const { seasonStartYear, team, prediction, wager } = req.body;
			const { rows } = await pool.query(query, [
				seasonStartYear,
				team,
				prediction,
				wager,
			]);

			res.json({ success: true, data: rows });
		} catch (error) {
			// Figure out which file imported this helper (for logging only)
			console.error(`Error in ${getCallerFile()} route handler:`, error);
			res.status(500).json({ success: false, message: error.message });
		}
	});

	return router;
}

// Helper function (for better error logging)
function getCallerFile() {
	let callerFile = "unknown";
	try {
		const parent = module.parent || module; // fallback if undefined
		callerFile = path.basename(parent.filename);
	} catch (_) {}
	return callerFile;
}

module.exports = createQueryRoute;
