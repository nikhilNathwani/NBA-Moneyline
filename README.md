# NBA Moneyline

Simulates a simple NBA betting strategy against historical moneyline odds: pick a team, season, prediction direction (bet on win vs. bet on loss), and wager size, and see what the season result would have been.

Shipped two ways:

| | Link | Stack |
|---|---|---|
| **Tableau dashboard** | [public.tableau.com/…/NBAMoneyline](https://public.tableau.com/views/NBAMoneyline/NBAMoneyline) | Tableau Public — parameter-driven calculated fields, a running-total table calc, a favorite/underdog breakdown |
| **Web app** | [nba-moneyline.vercel.app](https://nba-moneyline.vercel.app) | Node/Express + PostgreSQL + vanilla JS, deployed on Vercel |

Both are fed by the same Python/Selenium data pipeline (`data/`). The rest of this README covers the web app; see [Tableau dashboard](#tableau-dashboard) below for that version.

## Overview

The **web app** lets a user choose a team, season, prediction direction (bet on win vs bet on loss), and wager size, then computes what the season result would have been. It combines:

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
- Tableau Public (for the dashboard version — see below)

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
  scrape/                     # Step 1: OddsPortal scraping
  validate/                   # Steps 2-2.5: check the scraped data
  publish/                    # Steps 3-5: migrate to production, update frontend
  util/                       # Shared data model, constants, and output formatting
  tests/                      # pytest suite (parsing, validation, migration)
  README.md                   # Setup, the yearly run, troubleshooting

tableau/
  NBA Moneyline.twbx          # Published Tableau Public workbook
  games.csv                   # Data export the workbook reads
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

Requires Node 24 (pinned in `.nvmrc`; fnm switches to it automatically).

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

1. Scrape one season from OddsPortal
2. Verify game counts against that season's expected pattern, and every team's
   opponents against basketball-reference's schedule
3. Migrate into PostgreSQL in one all-or-nothing transaction (only with all checks
   passing, or an explicit override); the table's own constraints
   reject bad rows too
4. Update frontend season options

See [`data/README.md`](data/README.md) for setup, the yearly run, and troubleshooting.

## Tableau dashboard

`tableau/NBA Moneyline.twbx` is the published workbook
([Tableau Public](https://public.tableau.com/views/NBAMoneyline/NBAMoneyline)) —
a data-analyst-portfolio rebuild of the same simulator.

- Reads `tableau/games.csv`, an export of the pipeline's PostgreSQL data (30 teams, seasons 2016–2025, ~24k team-games with odds).
- The payout and ROI math the web app does in `resultSummary.sql` is reimplemented as Tableau calculated fields, driven by Team / Season / Prediction / Wager parameters.
- Adds a cumulative-profit line and a favorite/underdog diverging-bar breakdown — neither exists in the web app.

To edit: open the `.twbx` from this folder (not Tableau's default Workbooks folder) so the repo stays the source of truth, and re-publish to Tableau Public from here (same workbook name → replaces the existing viz, URL preserved). Custom team-logo shapes live in `~/Documents/My Tableau Repository/Shapes/NBA/` (Tableau requires shape sources there); the published `.twbx` bundles them.

Annual data refresh: `python3 data/publish/export_tableau_csv.py` regenerates `games.csv` from Postgres — see [`data/README.md`](data/README.md#afterwards-refresh-the-tableau-dashboard).

## Testing and Validation

For manual verification steps (API checks, local server checks, scraper-safe checks), see `TESTING.md`.

## Why This Project

This project demonstrates full-stack ownership across data engineering, backend API design, and UI performance. It reflects practical engineering tradeoffs (query simplification, route abstraction, and data integrity verification) in a production-style workflow.

The Tableau rebuild takes the same analysis to a data-analyst audience: the same pipeline and validation, with the modeling in calculated fields and parameters instead of SQL, and visualizations the web app never had.
