# NBA Moneyline Data Pipeline

Scrapes a season of NBA moneyline odds and results from OddsPortal, checks the
data, and loads it into the production Postgres database that the web app and
the Tableau dashboard read. It runs once a year, after a regular season ends.

## Layout

```
data/
  main.py             The whole pipeline, steps 1-6 in order - start here
  extract/            Step 1: get the season from both sources
    oddsportal/           OddsPortal: odds and results, two rows per game
    basketball_reference/ the official schedule - dates, home/away
                        Each has scraper.py (gets the pages; OddsPortal's needs a
                        real browser) and parser.py (reads them - pure, tested
                        against saved pages)
  validate/           Step 2: check the scraped data against expectations and
                      the official schedule (verification.py)
  transform/          Step 3: turn the two rows per game into one record per
                      real game, dated from the official schedule (build_game_records.py)
  load/               Steps 4-6: load into Postgres, update the web app's season
                      list, final check; plus the Tableau CSV export
  util/               Shared pieces: the TeamGame record (team_game.py - one
                      team's side of a game), constants (the project root,
                      expected game counts per season), console output
  tests/              The pytest suite - checks the *code*, never runs during
                      the pipeline. Mirrors the folders above
  sample_queries.sql  Handy SQL for inspecting the database by hand
  .python-version     The Python version the venv is built with (read by uv)
  pytest.ini          Lets tests import the code the way main.py does
```

(`.python-version` and `pytest.ini` are hidden in this project's VS Code sidebar;
they're set-and-forget.)

`validate/` vs. `tests/`: `validate/` is part of the pipeline and checks each
season's *data* every run; `tests/` checks that the code itself works.

To poke at the database by hand, `sample_queries.sql` has ready-made queries
(seasons, a team's season, records against each opponent, structure, sizes).

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

### Step 1: Extract from both sources

-   **OddsPortal**: opens Chrome on the season's NBA results pages and reads every
    regular-season game (two rows per game, one per team), switching the site to
    American odds first. Each page is retried up to 3 times if it doesn't fully
    load, and cached once it passes (see "scrape aborted mid-run" below). From
    2023-24 on it also reads the NBA Cup page, because OddsPortal lists the
    tournament's quarterfinals and semifinals there instead of with the NBA results;
    they count toward the 82-game season (the final doesn't, and is left out). A
    game listed without odds gets the average of the bookmakers on its own page.
-   **basketball-reference**: downloads every team's official schedule (play-in
    games excluded) - the source of each game's date and home team, and what
    Step 2 checks opponents against. This needs network access to
    basketball-reference.com: without it the season can't be loaded, since the
    database needs each game's date.

### Step 2: Validate

First, each team's game count against that season's expected pattern
(`util/constants.py`), with an explicit pass/fail:

```
✅ Total team-game rows scraped: 2460 (expected 2460; 2 per game)

📋 Games Per Team:
  Atlanta Hawks................................. 82 games
  [... all 30 teams ...]

✅ Per-team distribution matches expectations: 30 teams @ 82
```

-   The scraper produces two rows per game, one per team, so 2,460 rows = 1,230 games.
-   Seasons are checked against their own format: all 30 at 82 normally (since
    2023-24 that includes the NBA Cup quarterfinals and semifinals), all 30 at 72
    in 2020-21. 2019-20 (the COVID bubble) has no fixed
    pattern, so the count check doesn't apply and the opponent check below is the
    check.

Then every team's scraped opponents against the official schedule:

```
✅ All 30 teams' scraped opponents match the authoritative schedule
```

A mismatch lists the exact missing/extra opponents for that team. This
comparison ignores order; Step 3 handles order.

### Step 3: Transform

Every game is matched to its entry on basketball-reference's schedule, which turns
the scraper's two rows into one record with the game's real date and home team
(`transform/build_game_records.py`):

```
📅 Matched all 1230 games to their dates on basketball-reference
```

The match needs both teams' rows to agree: right opponents, right winner, mirrored
odds, close to the right place in each team's schedule, and within a day of the
real date (OddsPortal's dates can run a day ahead). Games listed out of date order,
a team with a game missing, and the same teams on consecutive days all still match,
and game numbers come from the real dates. If any game can't be matched to exactly one pair of rows, it
says which, and the season can't be migrated - nothing is guessed.

### Step 4: Confirm and load

If every check passed:

```
All checks passed. Ready to migrate 2025-26 data to Vercel Postgres? (Y/n):
```

If a check failed, it lists what failed and migrating takes typing
`migrate anyway`; Enter (or anything else) cancels:

```
❌ Not all checks passed for 2025-26:
    - game counts don't match the expected distribution (Step 2)

Type 'migrate anyway' to migrate 2025-26 regardless, or press Enter to cancel:
```

Override only when you've confirmed the data is right and the expectation is
what's wrong (e.g. the league changed its format). If basketball-reference couldn't
be downloaded or a game couldn't be matched to its date, there's no override: the
season can't be migrated without dates.

The migration deletes the season's existing games, inserts the new ones (one row
per game; odds as plain integers like `150` / `-200`, and the web app adds the `+`
for display), then checks the whole season: all 30 teams play, and no team plays
twice on one date. It's all one transaction, so any failure leaves production
exactly as it was, and the tables' own constraints (see [The database](#the-database))
reject bad rows the same way. Re-running a season is safe.

### Step 5: Update the web app

Adds the season to the web app's dropdown (`public/js/view/renderFilters.js`),
then commits and pushes ("Add 2025-26 season to web app"), which deploys it on
Vercel.

### Step 6: Final database check

```
📊 Games Per Season in Database:
  2016-17:......................................... 1230 games
  ...
  2025-26:......................................... 1230 games
  ─────────────────────────────────────────────────────────
  TOTAL:........................................... 11979 games
```

### Afterwards: refresh the Tableau dashboard

The dashboard (`tableau/NBA Moneyline.twbx`) reads `tableau/games.csv`, which the
migration does **not** update:

```bash
python3 data/load/tableau_csv.py   # from the project root: regenerates tableau/games.csv
git add tableau/games.csv && git commit -m "Add <season> to Tableau data export"
```

Then in Tableau:

1. Open `tableau/NBA Moneyline.twbx`, then **refresh the extract**: Data menu ->
   the `games` data source -> Extract -> Refresh. The dashboard reads a snapshot
   of the CSV saved inside the workbook, not the CSV itself, so without this step
   re-publishing uploads the old data. (New CSV columns also only appear after it.)
2. Add the new season to the **Season Start Year Parameter** list (Data pane ->
   right-click -> Edit). Once dynamic parameters point at the field this should
   update on open, but confirm.
3. Check a worked example still holds (e.g. Boston Celtics 2023-24, win every
   game, $100 -> +$22.39, +0.27% ROI, 64-18 - their official record, including
   the NBA Cup quarterfinal they lost).
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
local Postgres and copy the current definitions of the `teams` and `games` tables
and the `team_games` view from production into it (production is only read, never
written), so they always test against the real columns and constraints. They're skipped if Postgres isn't installed
locally or production can't be reached.

## The database

*As of 2026-10-04. The database itself is the source of truth (the migration tests
read its definitions live); update this section when you change it.*

Written by the pipeline, read by the web app (`app/queries/`) and the Tableau export.
(The same Postgres database also holds Titan Tracker's three `titan*` tables.)

**`teams`**: one row per franchise.

| Column | Type | Meaning |
|---|---|---|
| `team_id` | smallint | primary key |
| `name` | varchar(255) | e.g. "Boston Celtics" (unique) |

**`games`**: one row per real game.

| Column | Type | Meaning |
|---|---|---|
| `game_id` | integer | primary key (generated) |
| `seasonstartyear` | integer | year the season started (2025 = 2025-26) |
| `game_date` | date | when it was played (from basketball-reference) |
| `home_team_id`, `away_team_id` | smallint | references `teams` |
| `neutral_site` | boolean | played at a neutral venue (e.g. abroad); home/away is then alphabetical, for structure only |
| `home_won` | boolean | true if the home team won |
| `home_odds`, `away_odds` | integer | American moneyline odds on each team winning (e.g. 150, -200) |

All columns are NOT NULL. Constraints: home and away teams must exist in `teams` and
differ; a team can't be home twice (or away twice) on one date; the date must fall
within the season; odds must be valid American odds (-100 or below, or 100 or above).

**`team_games`** (a view): each game from both teams' sides - two rows per game,
the shape the web app and Tableau use. Columns: `team`, `seasonstartyear`,
`gamenumber` (the team's Nth game, numbered by date), `outcome` (true if `team`
won), `winodds`, `loseodds` (= the opponent's `winodds`), `opponent`, `game_date`,
`is_home` (null for neutral sites), `game_id`. A view stores nothing itself; it's a
saved query over `games` and `teams`, so it can't drift from them.

Whole-season rules (all 30 teams play, no team plays twice on one date) span many
rows, so the migration checks them (`load/postgres.py`).

History (2026-10-04):
-   The odds columns changed from text (`"+150"`) to integer, and the table got its
    first constraints.
-   The single `games` table (two rows per game, no dates or opponents) was
    replaced by `teams` + one-row-per-game `games` + the `team_games` view. Every
    old row was matched to its real game on basketball-reference, confirmed by
    mirrored odds and winners, without re-scraping OddsPortal. The values were
    unchanged except 26 game numbers in 2025-26 (see Notes).
-   The NBA Cup quarterfinals and semifinals for 2023-24, 2024-25 and 2025-26 (6
    per season, 18 games) were added, so every team in those seasons has 82 games.
    They were scraped from OddsPortal's NBA Cup pages and loaded through the same
    checks; no existing game was changed. Their odds are OddsPortal's averages as of
    that date (from 1, 2 and 3 bookmakers respectively - see Notes).

The web app reads these live, so for any structural change, deploy app code that
works with both the old and new structure first, then change the database.

## Troubleshooting

### Game counts or opponents don't match (Step 2)

-   Check the regular season is actually complete.
-   The opponent check's output names the specific teams and opponents that are off - much
    faster than reading raw counts.
-   A game OddsPortal lists without odds is filled from its own page (the average
    of the bookmakers there); if that page has none either, the game is skipped and
    shows up here as missing. Check the game on OddsPortal.

### "N consecutive pages failed to render" / scrape aborted mid-run

-   OddsPortal is very likely rate-limiting or blocking automated requests; the
    scraper deliberately stops rather than produce an incomplete dataset.
-   Wait a while (at least tens of minutes; the exact cooldown isn't known) before
    re-running - retrying immediately may extend the block.
-   A re-run resumes: every page that loaded successfully is cached in
    `data/.oddsportal_cache/`. The cache is deleted once that season migrates.
-   If it keeps happening after a real wait, check in a normal browser whether
    OddsPortal's site structure changed (it was redesigned in 2026, which needed a
    scraper rewrite).

### Odds errors

-   "odds ... aren't in American format" means OddsPortal's odds-format setting
    didn't take (the scraper sets it in the browser's local storage as
    `op_oddsFormatId=3`); OddsPortal may have changed how it stores it.
-   Scraped data only lives in memory during a run: decline at Step 4, fix the
    scraper, and re-run rather than patching data mid-run.

### Migration fails

-   Check `POSTGRES_URL` in `.env.development.local` and your network connection.
-   A constraint name in the error (e.g. `games_home_team_once_per_day`,
    `games_home_odds_american`), "teams not in the teams table" or "season checks
    failed" means the data itself was rejected. Nothing was written,
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
-   **OddsPortal's odds aren't fixed over time**: they're averages across the
    bookmakers OddsPortal has on record for each game, and that set changes - as of
    October 2026 it was 1 bookmaker for 2023-24 games and 4 for 2025-26. Re-scraping
    2025-26 three months after it was loaded gave identical odds for only 101 of
    1,224 games, though the gaps were small (a median of 0.6 percentage points of
    implied win probability, at most 2.3). So each season's odds are a snapshot of
    when it was scraped (per git history: 2022-23 to 2024-25 in November 2025,
    2025-26 in July 2026, the 18 NBA Cup games in October 2026; earlier seasons
    before that).
-   **OddsPortal's listing order isn't always date order**: for 2025-26, five
    games (BOS-MIN Nov 29, ATL-PHI Dec 14, POR-UTA Jan 5, ATL-IND Jan 26, DEN-HOU
    Mar 11) were listed 1-3 places later than when they were played, so the old
    table had 26 rows' game numbers off. Game numbers now come from real dates, which
    fixed them. 2025-26 was the only season scraped from OddsPortal's generic
    "current results" page (the others came from archived season pages), the likely
    cause; not confirmed.
