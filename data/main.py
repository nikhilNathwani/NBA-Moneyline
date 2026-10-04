#!/usr/bin/env python3
"""
NBA Moneyline Data Pipeline - Main Script

This script orchestrates the complete workflow:
1. Scrape NBA moneyline data from OddsPortal for the specified season
2. Verify the scraped data (game counts per team)
3. Prompt user to confirm migration
4. Migrate data to Vercel Postgres database
5. Update frontend seasons list and push to git
6. Verify migration was successful

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

from scrape.odds.scraper import OddsPortalScraper
from validate.verification import verify_scraped_data, validate_scraped_data_against_schedule
from publish.migrate_to_production import (
    verify_postgres_migration,
    migrate_season_to_postgres
)
from publish.update_frontend import (
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
        description='Complete NBA Moneyline data pipeline: scrape, verify, and migrate',
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
    parser.add_argument(
        '--skip-schedule-validation',
        action='store_true',
        help='Skip comparing scraped opponents against basketball-reference\'s authoritative schedule'
    )

    args = parser.parse_args()
    season = args.season

    print_section_header("🏀 NBA MONEYLINE DATA PIPELINE")
    print(f"Season: {season}-{(season+1)%100:02d}\n")

    # Cache dirs computed unconditionally (regardless of --skip-schedule-validation
    # or where a failure happens) so cleanup after a successful migration can
    # always find them, whether or not they ended up being used this run.
    odds_cache_dir = os.path.join(DATA_DIR, '.oddsportal_cache', str(season))
    bbref_cache_dir = os.path.join(DATA_DIR, '.bbref_cache', str(season))

    season_migrated = False
    season_games = None

    # Step 1: Scrape data
    print_section_header(f"STEP 1: SCRAPING {season}-{(season+1)%100:02d} SEASON")

    scraper = OddsPortalScraper(headless=args.headless)
    try:
        season_games = scraper.scrapeSeasonSchedule(season, cache_dir=odds_cache_dir)
    except RuntimeError as e:
        print(f"\n❌ Scraping {season}-{(season+1)%100:02d} aborted: {e}")
        print(f"⏭️  Pages that rendered successfully before the abort are cached for the next run.")

    if season_games is not None:
        # Step 2: Verify scraped data
        print_section_header("STEP 2: VERIFYING SCRAPED DATA")

        verification_results = verify_scraped_data(season_games, season)
        print_verification_results(season, verification_results)

        # Every reason this season shouldn't migrate without a deliberate
        # override. A check that couldn't run counts too - only skipping
        # schedule validation on purpose (the flag) doesn't.
        failed_checks = []
        has_count_expectation = verification_results['distribution_ok'] is not None
        if has_count_expectation and not (verification_results['total_games_ok']
                                          and verification_results['distribution_ok']):
            failed_checks.append("game counts don't match the expected distribution (Step 2)")

        # Step 2.5: Validate scraped opponents against the authoritative schedule
        if args.skip_schedule_validation:
            if not has_count_expectation:
                failed_checks.append("this season has no fixed game-count expectation and "
                                     "schedule validation was skipped, so nothing was checked")
        else:
            print_section_header("STEP 2.5: VALIDATING AGAINST AUTHORITATIVE SCHEDULE")

            try:
                schedule_comparisons = validate_scraped_data_against_schedule(
                    season_games, season, cache_dir=bbref_cache_dir)
                print_schedule_validation_results(season, schedule_comparisons)
                mismatched = [c for c in schedule_comparisons if not c.ok]
                if mismatched:
                    failed_checks.append(f"{len(mismatched)} teams' opponents don't match "
                                         f"basketball-reference (Step 2.5)")
            except Exception as e:
                print(f"\n⚠️  Schedule validation failed ({e.__class__.__name__}: {e}).")
                failed_checks.append(f"schedule validation couldn't run ({e.__class__.__name__})")

        # Step 3: Prompt for migration - a plain Y/Enter only when every check
        # passed; otherwise migrating takes typing an explicit override.
        print_section_header("STEP 3: MIGRATION TO VERCEL POSTGRES")

        season_str = f"{season}-{(season+1)%100:02d}"
        if not failed_checks:
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
                inserted = migrate_season_to_postgres(season_games, season)
                print(f"\n✅ Migration complete: {inserted} team-game rows inserted ({inserted // 2} games)")
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

    # Step 4: Update frontend with the new season
    if season_migrated:
        print_section_header("STEP 4: UPDATING FRONTEND SEASONS LIST")

        if update_seasons_list(season):
            season_str = f"{season}-{(season+1)%100:02d}"
            print(f"📝 Added {season_str} to frontend seasons list")

            if commit_and_push_changes(season):
                print(f"✅ Changes committed and pushed to git")
            else:
                print(f"⚠️  Git operation failed (changes may need manual commit)")
        else:
            print(f"ℹ️  Season already exists in frontend, no update needed")

    # Step 5: Final verification
    print_section_header("STEP 5: FINAL DATABASE VERIFICATION")

    postgres_results = verify_postgres_migration()
    print_postgres_verification(postgres_results)

    print_section_header("✅ PIPELINE COMPLETE!")


if __name__ == "__main__":
    main()
