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
✅ Total Games Scraped: 2448 (expected 2448)

📋 Games Per Team:
  Atlanta Hawks................................. 82 games
  New York Knicks............................... 80 games
  [... all 30 teams ...]

✅ Per-team distribution matches expectations: 22 teams @ 82, 4 teams @ 81, 4 teams @ 80
```

**What to check:**

-   Total should be 2,448 games (30 teams × 82, minus 12 excluded in-season-tournament
    knockout games: the 4 IST semifinalists each play 2 knockout games and land on 80,
    the 4 teams eliminated in the IST quarterfinal each play 1 and land on 81, the
    remaining 22 teams are unaffected at 82). If a season doesn't have an in-season
    tournament, expect all 30 teams at 82 (2,460 total) instead.
-   The pass/fail line should say ✅. If it doesn't, the printed mismatches tell you
    which teams/counts are off - don't proceed to migration until this is resolved.

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

You'll be prompted:

```
Ready to migrate 2024-25 data to Vercel Postgres? (Y/n):
```

-   Review the stats above
-   Type `Y` and press Enter to proceed
-   Type `n` to cancel and investigate issues

### Step 4: Migration to Database

-   Deletes any existing data for this season in Postgres
-   Converts data types:
    -   `outcome`: INTEGER (0/1) → BOOLEAN
    -   `winOdds/loseOdds`: INTEGER → VARCHAR with +/- prefix
-   Inserts all games into production database
-   Shows count of inserted games

### Step 5: Update Frontend

-   Adds the new season to the dropdown in the web app (via public/js/view/renderFilters.js)
-   Git commits and pushes the change automatically
-   Message: "Add 2024-25 season to web app"

### Step 6: Final Verification

Displays all seasons in your database:

```
📊 Games Per Season in Database:
  2016-17:......................................... 2460 games
  2017-18:......................................... 2460 games
  ...
  2024-25:......................................... 2448 games
  2025-26:......................................... 2448 games ✨ NEW
  ─────────────────────────────────────────────────────────
  TOTAL:........................................... 23922 games
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
-   Data only exists in memory for the duration of a run - type `n` at the Step 3
    prompt to decline migration, fix the underlying scraper issue, and re-run
    from scratch rather than trying to patch the data mid-run

### Migration fails

-   Check `.env.development.local` has valid `POSTGRES_URL`
-   Verify network connection to Vercel
-   Check error message for specific issue

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
pip install -r requirements.txt
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
-   **Idempotent**: Safe to re-run if something goes wrong (deletes old data first)
-   **Web App**: New season will automatically appear in dropdown after migration
-   **Tests**: `pytest data/test/` runs the parsing/comparison logic against saved
    fixtures with no network access - worth running after any scraper changes

## Need Help?

Check the main script for detailed error messages:

```bash
python3 main.py --help
```
