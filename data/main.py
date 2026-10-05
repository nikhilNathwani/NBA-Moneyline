#!/usr/bin/env python3
"""
NBA Moneyline Data Pipeline - Main Script

This script orchestrates the complete workflow:
1. Extract the season: odds and results from OddsPortal, and the
   official schedule (dates, home/away) from basketball-reference  - extract/
2. Validate: game counts per team, and every team's opponents
   against the official schedule                                    - validate/
3. Transform: turn the scraper's two rows per game into one
   record per real game, dated from the official schedule           - transform/
4. Confirm, then load into the Vercel Postgres database            - load/
5. Update frontend seasons list and push to git                    - load/
6. Verify the load was successful                                  - load/

One season per run, by design - catching up multiple seasons after a gap
just means running this multiple times. OddsPortal is already slow and
rate-limit-prone for a single season; depending on it for several in one
run isn't worth it, and running seasons as separate invocations means a
failure on one never risks work already completed on another.

Usage:
    python3 main.py --season 2024
    python3 main.py --season 2024 --headless
"""

import os
import sys
import shutil
import argparse

# Fail fast with setup instructions if the venv is missing packages, rather
# than installing anything as a side effect (see README.md's Setup section)
def check_requirements():
    """Exit with venv setup instructions if a required package is missing."""
    try:
        import psycopg2
        import selenium
        import bs4
        from dotenv import load_dotenv
    except ImportError as e:
        sys.exit(
            f"❌ Missing package '{e.name}' - is the venv set up and activated? From data/:\n"
            f"    uv venv --managed-python .venv\n"
            f"    uv pip install --python .venv/bin/python -r requirements.txt\n"
            f"    source .venv/bin/activate"
        )

check_requirements()

from extract.oddsportal.scraper import OddsPortalScraper
from extract.basketball_reference.fetcher import load_true_schedules
from validate.verification import verify_scraped_data, validate_scraped_data_against_schedule
from transform.build_game_records import match_to_schedule, MatchError
from load.postgres import (
    verify_postgres_migration,
    migrate_season_to_postgres
)
from load.web_app import (
    update_seasons_list,
    commit_and_push_changes
)
from util.console_output import (
    print_section_header,
    print_verification_results,
    print_schedule_validation_results,
    print_postgres_verification
)


# Directory this script lives in, used for the OddsPortal page cache and the
# basketball-reference schedule cache
DATA_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(
        description='NBA Moneyline data pipeline: extract, validate, transform, and load one season',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--season',
        type=int,
        required=True,
        help='Season start year to scrape (e.g., 2024 for the 2024-25 season)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )

    args = parser.parse_args()
    season = args.season

    print_section_header("🏀 NBA MONEYLINE DATA PIPELINE")
    print(f"Season: {season}-{(season+1)%100:02d}\n")

    # Cache dirs computed unconditionally (regardless of where a failure
    # happens) so cleanup after a successful migration can always find them.
    odds_cache_dir = os.path.join(DATA_DIR, '.oddsportal_cache', str(season))
    bbref_cache_dir = os.path.join(DATA_DIR, '.bbref_cache', str(season))

    season_migrated = False
    season_games = None

    season_str = f"{season}-{(season+1)%100:02d}"
    schedules = None
    schedules_error = None

    # Step 1: Extract from both sources - OddsPortal (odds and results) and
    # basketball-reference (the official schedule: dates and home/away)
    print_section_header(f"STEP 1: EXTRACTING {season_str} SEASON")

    print("📥 OddsPortal (odds and results)\n")
    scraper = OddsPortalScraper(headless=args.headless)
    try:
        season_games = scraper.scrapeSeasonSchedule(season, cache_dir=odds_cache_dir)
    except RuntimeError as e:
        print(f"\n❌ Scraping {season_str} aborted: {e}")
        print(f"⏭️  Pages that rendered successfully before the abort are cached for the next run.")

    if season_games is not None:
        print("📥 basketball-reference (official schedule)")
        try:
            schedules = load_true_schedules(season, cache_dir=bbref_cache_dir)
            print(f"✅ Downloaded all {len(schedules)} teams' schedules")
        except Exception as e:
            schedules_error = f"{e.__class__.__name__}: {e}"
            print(f"❌ Couldn't download basketball-reference's schedule ({schedules_error})")

        # Step 2: Validate the scraped data
        print_section_header("STEP 2: VALIDATING SCRAPED DATA")

        verification_results = verify_scraped_data(season_games, season)
        print_verification_results(season, verification_results)

        # Every reason this season shouldn't migrate without a deliberate
        # override (the data might still be right and the expectation wrong)
        failed_checks = []
        if verification_results['distribution_ok'] is False or verification_results['total_games_ok'] is False:
            failed_checks.append("game counts don't match the expected distribution (Step 2)")
        # Set if migrating is impossible, not just unadvised: the games
        # table needs each game's date, which only Step 3 provides
        cannot_migrate = None
        records = None

        if schedules is None:
            cannot_migrate = (f"basketball-reference's schedule couldn't be downloaded in Step 1 "
                              f"({schedules_error}), and it's needed to date each game")
        else:
            schedule_comparisons = validate_scraped_data_against_schedule(season_games, schedules)
            print_schedule_validation_results(season, schedule_comparisons)
            mismatched = [c for c in schedule_comparisons if not c.ok]
            if mismatched:
                failed_checks.append(f"{len(mismatched)} teams' opponents don't match "
                                     f"basketball-reference (Step 2)")

            # Step 3: Transform - turn the scraper's two rows per game into
            # one record per real game, dated from basketball-reference
            print_section_header("STEP 3: TRANSFORMING: ONE DATED RECORD PER GAME")
            try:
                match = match_to_schedule(season_games, schedules)
                records = match.records
                print(f"📅 Matched all {len(records)} games to their dates on basketball-reference"
                      + (f" ({match.listed_out_of_order} weren't in date order on OddsPortal, "
                         f"so their game numbers come from the real dates)" if match.listed_out_of_order else ""))
            except MatchError as e:
                print(f"\n❌ Couldn't match every game to basketball-reference's schedule: {e}")
                cannot_migrate = f"not every game could be matched to its date ({e})"

        # Step 4: Prompt for migration - a plain Y/Enter only when every check
        # passed; otherwise migrating takes typing an explicit override.
        print_section_header("STEP 4: LOADING INTO VERCEL POSTGRES")

        if cannot_migrate:
            print(f"❌ Can't migrate {season_str}: {cannot_migrate}.")
            if failed_checks:
                print("Other checks that failed:")
                for reason in failed_checks:
                    print(f"    - {reason}")
            proceed = False
        elif not failed_checks:
            response = input(f"All checks passed. Ready to migrate {season_str} data to Vercel Postgres? (Y/n): ")
            proceed = response.strip().upper() in ['Y', 'YES', '']
        else:
            print(f"❌ Not all checks passed for {season_str}:")
            for reason in failed_checks:
                print(f"    - {reason}")
            response = input(f"\nType 'migrate anyway' to migrate {season_str} regardless, or press Enter to cancel: ")
            proceed = response.strip().lower() == 'migrate anyway'

        if proceed:
            print(f"\n🚀 Starting migration for {season}-{(season+1)%100:02d}...\n")

            try:
                inserted = migrate_season_to_postgres(records, season)
                print(f"\n✅ Migration complete: {inserted} games inserted")
                season_migrated = True

                # Data is safely in production now - the local scrape caches
                # (kept until now purely so a failure could resume cheaply)
                # are no longer needed.
                for cache_dir in (odds_cache_dir, bbref_cache_dir):
                    if os.path.isdir(cache_dir):
                        shutil.rmtree(cache_dir)
                print(f"🧹 Cleaned up local scrape caches for {season}-{(season+1)%100:02d}")
            except Exception as e:
                print(f"\n❌ Migration failed and was rolled back - production data is unchanged: {e}")
        else:
            print(f"\n⏭️  Skipping migration for {season}-{(season+1)%100:02d}")

    # Step 5: Update frontend with the new season
    if season_migrated:
        print_section_header("STEP 5: UPDATING FRONTEND SEASONS LIST")

        if update_seasons_list(season):
            print(f"📝 Added {season_str} to frontend seasons list")

            if commit_and_push_changes(season):
                print(f"✅ Changes committed and pushed to git")
            else:
                print(f"⚠️  Git operation failed (changes may need manual commit)")
        else:
            print(f"ℹ️  Season already exists in frontend, no update needed")

    # Step 6: Final verification
    print_section_header("STEP 6: FINAL DATABASE VERIFICATION")

    postgres_results = verify_postgres_migration()
    print_postgres_verification(postgres_results)

    print_section_header("✅ PIPELINE COMPLETE!")


if __name__ == "__main__":
    main()
