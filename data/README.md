# NBA Moneyline Data Pipeline

Scrapes a season of NBA moneyline odds and results from OddsPortal, checks the
data, and loads it into the production Postgres database that the web app and
the Tableau dashboard read. It runs once a year, after a regular season ends.

## Layout

```
data/
  main.py          The whole pipeline, steps 1-5 in order - start here
  scrape/odds/     Step 1: scrape OddsPortal (Selenium) and turn each game into
                   two team rows (scraper.py drives the browser; parser.py is
                   the pure HTML parsing)
  validate/        Steps 2-2.5: check the scraped data before it's trusted
                   (verification.py), against basketball-reference's schedule
                   (schedules/)
  publish/         Steps 3-5: migrate to Postgres, update the web app's season
                   list, export the CSV that Tableau reads
  util/            Shared pieces: the Game record, expected game counts per
                   season (constants.py), console output
  schema.sql       The production `games` table and its constraints
  tests/           The pytest suite - checks the *code*, never runs during the
                   pipeline. Mirrors the folders above (tests/scrape/,
                   tests/validate/, tests/publish/)
```

`validate/` vs. `tests/`: `validate/` is part of the pipeline and checks each
season's *data* every run; `tests/` checks that the code itself works.

## One-time setup

**Python environment** (uses the Python version pinned in `.python-version`):

```bash
cd data
uv venv --managed-python .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

If `.venv/bin/python` or `pytest` ever fails with "cannot execute" / "No such file
or directory", the folder was moved or renamed after the venv was created (venvs
embed their absolute path). Recreate it: `rm -rf .venv`, then the two commands above.

**Database credentials**: the pipeline reads `POSTGRES_URL` from
`.env.development.local` in the project root. Pull it from Vercel with
`npm run sync-env` (from the project root).

**Chrome**: just have Google Chrome installed. Selenium downloads a matching
driver automatically (into `~/.cache/selenium`).

**Adding a Python package**: add it with a pinned version to the "direct
dependencies" section of `requirements.txt` (the file is organized by hand -
don't overwrite it with `uv pip freeze`), then re-run the `uv pip install` line above.

## Running the yearly update

Wait until the regular season is completely finished. Then:

```bash
cd data
source .venv/bin/activate
python3 main.py --season 2025            # season start year: 2025 = the 2025-26 season
python3 main.py --season 2025 --headless # same, without a visible browser window
```

One season per run, by design: catching up after a gap means one run per season
(see the note at the top of `main.py` for why). Other options: `python3 main.py --help`.

### Step 1: Scrape

Opens Chrome on OddsPortal's NBA results pages and scrapes every game of the
season into memory. Each page is checked for being fully loaded, retried up to 5
times if not, and cached once it passes (see "scrape aborted mid-run" below).

### Step 2: Check game counts

Compares each team's game count with that season's expected pattern
(`util/constants.py`), and prints an explicit pass/fail:

```
✅ Total team-game rows scraped: 2448 (expected 2448; 2 per game)

📋 Games Per Team:
  Atlanta Hawks................................. 82 games
  [... all 30 teams ...]

✅ Per-team distribution matches expectations: 22 teams @ 82, 4 teams @ 81, 4 teams @ 80
```

-   Every game is stored twice, once per team, so 2,448 rows = 1,224 games.
-   Since 2023-24, 8 teams finish below 82: in-season tournament (NBA Cup) knockout
    games are excluded, so the 4 semifinalists land on 80 and the 4 quarterfinal
    losers on 81. Which teams is detected each season, not hardcoded.
-   Older seasons are checked against their own format: all 30 at 82 before
    2023-24, all 30 at 72 in 2020-21. 2019-20 (the COVID bubble) has no fixed
    pattern, so this step just prints the counts and Step 2.5 is the check.

### Step 2.5: Check against basketball-reference

Compares every team's scraped opponents with basketball-reference.com's official
schedule (play-in and tournament knockout games excluded):

```
✅ All 30 teams' scraped opponents match the authoritative schedule
```

A mismatch lists the exact missing/extra opponents for that team. The comparison
ignores game order, so a postponed game doesn't cause a false alarm.
`--skip-schedule-validation` skips this step (e.g. no network access).

### Step 3: Confirm and migrate

If every check passed:

```
All checks passed. Ready to migrate 2025-26 data to Vercel Postgres? (Y/n):
```

If any check failed - including Step 2.5 crashing, or skipping Step 2.5 for a season
with no fixed count pattern, so that nothing was checked - it lists what failed and
migrating takes typing `migrate anyway`; Enter (or anything else) cancels:

```
❌ Not all checks passed for 2025-26:
    - game counts don't match the expected distribution (Step 2)

Type 'migrate anyway' to migrate 2025-26 regardless, or press Enter to cancel:
```

Override only when you've confirmed the data is right and the expectation is
what's wrong (e.g. the league changed its format).

The migration deletes the season's existing rows, inserts the new ones (odds as
plain integers like `150` / `-200`; the web app adds the `+` for display), then
checks the whole season: 30 teams, wins = losses, each team's game numbers 1..N with
no gaps. It's all one transaction, so any failure leaves production exactly as it
was, and the table's constraints (`schema.sql`) reject bad rows the same way.
Re-running a season is safe.

### Step 4: Update the web app

Adds the season to the web app's dropdown (`public/js/view/renderFilters.js`),
then commits and pushes ("Add 2025-26 season to web app"), which deploys it on
Vercel.

### Step 5: Final database check

```
📊 Team-Game Rows Per Season in Database (2 per game):
  2016-17:......................................... 2460 rows
  ...
  2025-26:......................................... 2448 rows
  ─────────────────────────────────────────────────────────
  TOTAL:........................................... 23922 rows
```

### Afterwards: refresh the Tableau dashboard

The dashboard (`tableau/NBA Moneyline.twbx`) reads `tableau/games.csv`, which the
migration does **not** update:

```bash
python3 data/publish/export_tableau_csv.py   # from the project root: regenerates tableau/games.csv
git add tableau/games.csv && git commit -m "Add <season> to Tableau data export"
```

Then in Tableau:

1. Open `tableau/NBA Moneyline.twbx` (the live connection reads the new CSV).
2. Add the new season to the **Season Start Year Parameter** list (Data pane ->
   right-click -> Edit). Once dynamic parameters point at the field this should
   update on open, but confirm.
3. Check a worked example still holds (e.g. Boston Celtics 2023-24, win every
   game, $100 -> +$122.39, +1.51% ROI, 64-17).
4. **File -> Save to Tableau Public**, same workbook name, replacing the existing
   viz - the URL (`public.tableau.com/views/NBAMoneyline/NBAMoneyline`) is kept.
5. Commit the updated `.twbx`.

Also visit the web app and check the new season works there.

## Tests

```bash
cd data && source .venv/bin/activate && pytest
```

Runs the parsing and checking logic against saved pages (no network access) -
worth running after any scraper change. The migration tests start a throwaway
local Postgres built from `schema.sql` (never production), and are skipped if
Postgres isn't installed.

## Troubleshooting

### Game counts don't match, or Step 2.5 reports mismatches

-   Check the regular season is actually complete.
-   Step 2.5's output names the specific teams and opponents that are off - much
    faster than reading raw counts.
-   Some end-of-season games may not have odds on OddsPortal.

### "N consecutive pages failed to render" / scrape aborted mid-run

-   OddsPortal is very likely rate-limiting or blocking automated requests; the
    scraper deliberately stops rather than produce an incomplete dataset.
-   Wait a while (at least tens of minutes; the exact cooldown isn't known) before
    re-running - retrying immediately may extend the block.
-   A re-run resumes: every page that loaded successfully is cached in
    `data/.oddsportal_cache/`. The cache is deleted once that season migrates.
-   If it keeps happening after a real wait, check in a normal browser whether
    OddsPortal's site structure changed.

### Missing or invalid odds warnings

-   Review the games mentioned; you may need to check them on OddsPortal.
-   Rows that needed the detail-page fallback have their HTML saved in
    `data/.oddsportal_cache/<season>/debug/` (deleted with the cache).
-   Scraped data only lives in memory during a run: decline at Step 3, fix the
    scraper, and re-run rather than patching data mid-run.

### Migration fails

-   Check `POSTGRES_URL` in `.env.development.local` and your network connection.
-   A constraint name in the error (e.g. `games_pkey`, `games_winodds_american`) or
    "season checks failed" means the data itself was rejected. Nothing was written,
    so fix the cause and re-run.

### Browser problems

-   Run without `--headless` to watch what's happening.
-   OddsPortal may have changed its site structure (the scraper may need updates).
-   "isn't archived under its own OddsPortal URL yet" is informational, not an error:
    the most recently finished season is only reachable via OddsPortal's generic
    current-results page until a newer season starts, and the scraper handles that.

## Notes

-   **No stored copies of the data**: scraped games live in memory during a run;
    Postgres is the only source of truth. The page caches (`data/.oddsportal_cache/`,
    `data/.bbref_cache/`) exist only so a failed run can resume cheaply - nothing
    reads data from them - and are deleted after a successful migration.
-   **Game order (open question, worth investigating some time)**: Step 2.5 ignores
    game order on purpose (decided 2026-07-16, commit `68dab74`) so postponed games
    don't cause false alarms. The side effect is that a team's game numbers can
    differ slightly from basketball-reference's order. A 2026-10-04 check of every
    season in production found game counts and wins matching for all 30 teams in
    all 10 seasons, and the game-by-game win/loss order matching in every season
    except 2025-26: there, 7 teams (ATL, BOS, DEN, HOU, IND, PHI, UTA) each have one
    pair of games in a different order. Season totals are unaffected; only those
    games' "Game #" labels (and the running-total line between them) differ. The
    cause isn't confirmed: postponements are the likely explanation, but checking
    needs a re-scrape of OddsPortal.
