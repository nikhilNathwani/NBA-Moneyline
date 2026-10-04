# Annual NBA Season Update Workflow

When a new NBA season ends and you want to add that year's data to your app.

## Quick Start

```bash
cd data
python3 main.py --season 2025
```

Replace `2025` with the season start year (e.g., for 2025-26 season, use 2025).

## What Happens

### Step 1: Scraping

-   Opens Chrome browser (or runs headless with `--headless` flag)
-   Navigates to OddsPortal.com NBA results pages
-   Scrapes all games for each team in the season, held in memory

### Step 2: Verification

Displays comprehensive stats and an explicit pass/fail against the expected
game-count distribution (see `util/constants.py`):

```
✅ Total team-game rows scraped: 2448 (expected 2448; 2 per game)

📋 Games Per Team:
  Atlanta Hawks................................. 82 games
  New York Knicks............................... 80 games
  [... all 30 teams ...]

✅ Per-team distribution matches expectations: 22 teams @ 82, 4 teams @ 81, 4 teams @ 80
```

**What to check:**

-   Total should be 2,448 team-game rows - each game is stored once per team, so 1,224
    games (30 teams × 82, minus 12 excluded in-season-tournament knockout games: the 4
    IST semifinalists each play 2 knockout games and land on 80, the 4 teams eliminated
    in the IST quarterfinal each play 1 and land on 81, the remaining 22 teams are
    unaffected at 82).
-   The expectation is looked up by season (`util/constants.py`), so re-running an older
    season checks it against that season's format: all 30 at 82 before 2023-24, all 30
    at 72 in 2020-21. 2019-20 (the COVID bubble) has no fixed pattern, so Step 2 just
    prints the counts and Step 2.5 is the check.
-   The pass/fail line should say ✅. If it doesn't, the printed mismatches tell you
    which teams/counts are off, and Step 3 won't migrate without an explicit override.

### Step 2.5: Schedule Validation

Cross-checks every team's scraped opponents against basketball-reference.com's
authoritative schedule (order-agnostic, so a legitimate game postponement/reschedule
won't false-positive):

```
✅ All 30 teams' scraped opponents match the authoritative schedule
```

If a team shows a mismatch, it lists the specific missing/extra opponents so you can
investigate that team's data directly rather than re-scraping blind. Skip this step
with `--skip-schedule-validation` if you don't have network access to
basketball-reference.com or want a faster run.

### Step 3: Confirmation

If every check passed, you'll be prompted:

```
All checks passed. Ready to migrate 2024-25 data to Vercel Postgres? (Y/n):
```

-   Review the stats above
-   Type `Y` (or just press Enter) to proceed
-   Type `n` to cancel and investigate issues

If any check failed - including Step 2.5 crashing, or skipping Step 2.5 for a season
with no fixed count expectation, so that nothing was checked - it lists what failed
instead, and migrating takes typing `migrate anyway`; Enter (or anything else) cancels:

```
❌ Not all checks passed for 2024-25:
    - game counts don't match the expected distribution (Step 2)

Type 'migrate anyway' to migrate 2024-25 regardless, or press Enter to cancel:
```

Override only when you've confirmed the data is right and the expectation is what's
wrong (e.g. the league changed its format).

### Step 4: Migration to Database

-   Deletes any existing data for this season in Postgres
-   Inserts all games into production database (odds as plain integers, e.g. `150` /
    `-200` - the web app adds the `+` for display)
-   Checks the whole season: 30 teams, wins = losses, each team's game numbers 1..N
    with no gaps
-   Shows count of inserted rows (2 per game)
-   All-or-nothing: the delete, inserts and season checks run in one transaction, so a
    failure leaves production exactly as it was. The table's own constraints
    (`data/schema.sql`) reject bad individual rows the same way

### Step 5: Update Frontend

-   Adds the new season to the dropdown in the web app (via public/js/view/renderFilters.js)
-   Git commits and pushes the change automatically
-   Message: "Add 2024-25 season to web app"

### Step 6: Final Verification

Displays all seasons in your database:

```
📊 Team-Game Rows Per Season in Database (2 per game):
  2016-17:......................................... 2460 rows
  2017-18:......................................... 2460 rows
  ...
  2024-25:......................................... 2448 rows
  2025-26:......................................... 2448 rows ✨ NEW
  ─────────────────────────────────────────────────────────
  TOTAL:........................................... 23922 rows
```

## Options

```bash
# Run in headless mode (no browser window)
python3 main.py --season 2025 --headless
```

Catching up multiple seasons after a gap means running this multiple times
(one invocation per season), not passing several seasons to one run - see
the note at the top of `main.py` for why.

## After Migration

1. **Check Vercel deployment** - Changes should auto-deploy, new season will appear in dropdown
2. **Test the web app** - Visit your site and verify the new season works correctly
3. **Check database** - Use the SQL scripts in `app/queries/sampleQueries.sql` if needed

### Refresh the Tableau dashboard

The Tableau version (`tableau/NBA Moneyline.twbx`) reads `tableau/games.csv`, a
flat export of the `games` table. The migration above does **not** touch it, so
it goes stale unless you do this:

```bash
python3 data/publish/export_tableau_csv.py   # regenerate tableau/games.csv from Postgres
git add tableau/games.csv && git commit -m "Add <season> to Tableau data export"
```

Then in Tableau:

1. Open `tableau/NBA Moneyline.twbx` (the live connection reads the new CSV automatically).
2. Add the new season to the **Season Start Year Parameter** list (Data pane -> right-click -> Edit).
   Once dynamic parameters are pointing at the field this should update on open, but confirm.
3. Verify a worked example still checks out (e.g. Boston Celtics 2023-24, win every game, $100
   -> +$122.39, +1.51% ROI, 64-17).
4. **File -> Save to Tableau Public**, same workbook name, replace the existing viz - the URL
   (`public.tableau.com/views/NBAMoneyline/NBAMoneyline`) is preserved.
5. Commit the updated `.twbx`.

## Troubleshooting

### Total doesn't match the expected count, or the distribution check fails

-   Check if regular season is actually complete
-   Re-run Step 2.5 (or `pytest data/test/`) - the schedule validation step will name
    the specific team(s)/opponent(s) that are off, which is much faster to debug than
    staring at raw counts
-   Some end-of-season games may not have odds on OddsPortal

### "N consecutive pages failed to render" / scrape aborted mid-run

-   This means OddsPortal is very likely rate-limiting or temporarily blocking automated
    requests (not a one-off timing glitch) - the scraper deliberately gives up rather
    than silently producing an incomplete dataset
-   Wait a while (the exact cooldown isn't known - at least tens of minutes) before
    re-running; re-running immediately is unlikely to help and may extend the block
-   Re-running isn't a full do-over: every page that rendered successfully before
    the abort is cached (`data/.oddsportal_cache/`), so the retry picks up from
    where it left off instead of re-scraping from page 1. The cache is cleared
    automatically once that season's migration succeeds
-   If it keeps happening after a real wait, check manually in a real (non-headless)
    browser whether OddsPortal's site structure changed

### Invalid odds warnings

-   Review the specific games mentioned
-   May need to manually check those games on OddsPortal
-   Rows whose odds needed the detail-page fallback have their HTML saved under
    `data/.oddsportal_cache/<season>/debug/` (deleted with the cache after a
    successful migration)
-   Data only exists in memory for the duration of a run - decline at the Step 3
    prompt, fix the underlying scraper issue, and re-run
    from scratch rather than trying to patch the data mid-run

### Migration fails

-   Check `.env.development.local` has valid `POSTGRES_URL`
-   Verify network connection to Vercel
-   Check error message for specific issue - a constraint name (e.g.
    `games_pkey`, `games_winodds_american`) or "season checks failed" means the data
    itself was rejected; nothing was written, so fix the cause and re-run

### Browser automation issues

-   Make sure Chrome/Chromium is installed
-   Try without `--headless` flag to see what's happening
-   Check if OddsPortal changed their site structure (may need code updates)
-   The scraper auto-detects whether the requested season is archived under its own
    OddsPortal URL yet, or still only reachable via the generic current-results page
    (this is expected/normal for whichever season was most recently completed) - if
    you see "isn't archived under its own OddsPortal URL yet", that's informational,
    not an error

## Prerequisites (One-time Setup)

### Python Packages

```bash
cd data
uv pip install --python .venv/bin/python -r requirements.txt
```

Required packages:

-   beautifulsoup4
-   selenium
-   lxml
-   psycopg2-binary
-   python-dotenv

### Chrome Browser

```bash
# macOS
brew install --cask chromedriver
```

### Environment File

Create `.env.development.local` in project root:

```
POSTGRES_URL=postgres://username:password@host/database
```

## Notes

-   **Timing**: Wait until regular season is completely finished
-   **In-Season Tournament**: Knockout-round (quarterfinal/semifinal) games are excluded;
    which teams/counts that affects is detected automatically each season (not hardcoded
    to a specific bracket), so this should keep working even if the bracket size changes
-   **No intermediate data storage**: scraped data itself lives in memory for the
    duration of a run and is never persisted locally; Postgres is the only source
    of truth, and a failed migration means re-running the whole pipeline (which is
    safe - see below). The pipeline does cache raw page HTML during scraping
    (`data/.oddsportal_cache/`, `data/.bbref_cache/`) purely so a re-run after a
    mid-scrape failure is cheap - neither verification nor migration ever reads
    from these caches, and both are deleted automatically once a season migrates
    successfully
-   **Game order (open question, worth investigating some time)**: Step 2.5 ignores
    game order on purpose (decided 2026-07-16, commit `68dab74`) so postponed games
    don't cause false alarms. The side effect is that a team's game numbers can differ
    slightly from basketball-reference's order. A 2026-10-04 check of every season in
    production found game counts and wins matching for all 30 teams in all 10 seasons,
    and the game-by-game win/loss order matching in every season except 2025-26: there,
    7 teams (ATL, BOS, DEN, HOU, IND, PHI, UTA) each have one pair of games in a
    different order. Season totals are unaffected; only those games' "Game #" labels
    (and the running-total line between them) differ. The cause isn't confirmed:
    postponements are the likely explanation, but checking needs a re-scrape of
    OddsPortal
-   **Idempotent**: Safe to re-run if something goes wrong (deletes old data first)
-   **Web App**: New season will automatically appear in dropdown after migration
-   **Tests**: `pytest data/test/` runs the parsing/comparison logic against saved
    fixtures with no network access - worth running after any scraper changes. The
    migration tests also start a throwaway local Postgres (never production) from
    `data/schema.sql`, and are skipped if Postgres isn't installed

## Need Help?

Check the main script for detailed error messages:

```bash
python3 main.py --help
```
