# NBA Moneyline

Web app that simulates a simple NBA betting strategy against historical moneyline odds.

## Overview

NBA Moneyline lets a user choose a team, season, prediction direction (bet on win vs bet on loss), and wager size, then computes what the season result would have been. The app combines:

- A Node/Express API for querying outcomes
- PostgreSQL for game and odds data
- Vanilla JavaScript frontend for fast interaction
- Python/Selenium scraping pipeline for annual data refresh

## Highlights

- SQL-driven profitability and ROI calculations
- Two focused API endpoints: result summary and top bets
- Shared Express route factory to keep backend handlers DRY
- Annual scraper workflow with verification and migration steps
- Production deployment pattern that mirrors local app behavior

## Tech Stack

- Node.js + Express
- PostgreSQL (`pg`)
- Vanilla JavaScript, HTML, CSS
- Python (Selenium, BeautifulSoup, psycopg2) for scraping/migration
- Vercel deployment

## Project Structure

```text
app/
  routes/
    resultSummary.js          # /api/result-summary
    topBets.js                # /api/top-bets
  utils/
    createQueryRoute.js       # Shared API route factory
    parseSQL.js               # Loads SQL files from disk
    dbConfig.js               # Shared PG pool
  queries/
    resultSummary.sql
    topBets.sql

public/
  index.html
  js/
    api/                      # Fetch + response adapters
    events/                   # Submit/interaction orchestration
    view/                     # Result rendering

data/
  main.py                     # End-to-end scrape, validate, and migrate flow
  scrape/                     # OddsPortal moneyline scraping
  storage/                    # SQLite save/verify, schedule validation, Postgres migration
  util/                       # Shared data model, constants, output, frontend update
  YEARLY_WORKFLOW.md          # Operational yearly procedure
```

## API Endpoints

- `POST /api/result-summary`
    - Input: `seasonStartYear`, `team`, `prediction`, `wager`
    - Output: aggregated outcomes grouped by favorite/underdog and result
- `POST /api/top-bets`
    - Input: same payload
    - Output: highest-earning individual bets for the chosen strategy

## Getting Started

### 1. Install Node dependencies

```bash
npm install
```

### 2. Configure environment

Create `.env.development.local` in the project root:

```bash
POSTGRES_URL=postgres://username:password@host/database
```

### 3. Run locally

```bash
npm run dev
```

App runs at http://localhost:3000.

## Scripts

```bash
npm start      # Production-style local start
npm run dev    # Development with nodemon
npm run sync-env
```

## Data Pipeline

The `data/` directory contains the yearly ingestion flow:

1. Scrape seasons from OddsPortal
2. Verify expected game counts
3. Migrate records into PostgreSQL
4. Update frontend season options

See `data/README.md` and `data/YEARLY_WORKFLOW.md` for full operational details.

## Testing and Validation

For manual verification steps (API checks, local server checks, scraper-safe checks), see `TESTING.md`.

## Why This Project

This project demonstrates full-stack ownership across data engineering, backend API design, and UI performance. It reflects practical engineering tradeoffs (query simplification, route abstraction, and data integrity verification) in a production-style workflow.
