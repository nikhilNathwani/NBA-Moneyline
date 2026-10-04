// This module exports a single shared PostgreSQL
// connection pool used by all routes

const { Pool } = require("pg");

// TODO (revisit when upgrading to pg v9): POSTGRES_URL comes from Vercel with
// sslmode=require, which pg 8 treats as verify-full (encrypted + certificate
// checked) and warns about on startup. pg 9 will treat it as standard libpq
// "require" (no certificate check). Before or during that upgrade, set the
// mode explicitly here (e.g. verify-full) - not in .env.development.local,
// which `npm run sync-env` overwrites.
const pool = new Pool({
	connectionString: process.env.POSTGRES_URL,
});

module.exports = pool;
