#!/usr/bin/env python3
"""
NBA Moneyline Data Pipeline - Main Script

This script orchestrates the complete workflow:
1. Scrape NBA moneyline data from OddsPortal for specified season(s)
2. Verify the scraped data (game counts per team)
3. Prompt user to confirm migration
4. Migrate data to Vercel Postgres database
5. Update frontend seasons list and push to git
6. Verify migration was successful

Usage:
    python3 main.py --seasons 2024
    python3 main.py --seasons 2023 2024
    python3 main.py --seasons 2024 --headless
"""

import os
import sys
import subprocess
import argparse
from typing import List

# Check and install requirements if needed
def check_requirements():
    """Check if required packages are installed, install if missing."""
    try:
        import psycopg2
        import selenium
        import bs4
        from dotenv import load_dotenv
    except ImportError:
        print("📦 Installing required packages...")
        requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', requirements_path], check=True)
        print("✅ Packages installed successfully\n")

check_requirements()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrape.odds.oddsportal_scraper import OddsPortalScraper
from scrape.utils.export_data import save_to_database
from scrape.utils.postgres_utils import (
    verify_scraped_data,
    verify_postgres_migration,
    migrate_season_to_postgres
)
from scrape.utils.schedule_validation import validate_scraped_data_against_schedule
from scrape.utils.console_output import (
    print_verification_results,
    print_schedule_validation_results,
    print_postgres_verification
)
from scrape.utils.update_frontend import (
    update_seasons_list,
    commit_and_push_changes
)


# Define output paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRAPE_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_seasons(seasons_arg: List[str]) -> List[int]:
    """Parse season arguments into list of season start years."""
    seasons = []
    for arg in seasons_arg:
        if '-' in arg:
            start, end = arg.split('-')
            seasons.extend(range(int(start), int(end) + 1))
        else:
            seasons.append(int(arg))
    return sorted(list(set(seasons)))


def main():
    parser = argparse.ArgumentParser(
        description='Complete NBA Moneyline data pipeline: scrape, verify, and migrate',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--seasons',
        nargs='+',
        required=True,
        help='Season start years to scrape (e.g., 2024 or 2023 2024)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser in headless mode'
    )
    parser.add_argument(
        '--skip-scrape',
        action='store_true',
        help='Skip scraping, only verify and migrate existing data'
    )
    parser.add_argument(
        '--skip-schedule-validation',
        action='store_true',
        help='Skip comparing scraped opponents against basketball-reference\'s authoritative schedule'
    )
    
    args = parser.parse_args()
    seasons = parse_seasons(args.seasons)
    
    print(f"\n{'='*70}")
    print(f"🏀 NBA MONEYLINE DATA PIPELINE")
    print(f"{'='*70}")
    print(f"Seasons: {', '.join(f'{s}-{(s+1)%100:02d}' for s in seasons)}\n")
    
    # Track successfully migrated seasons for frontend update
    migrated_seasons = []
    
    # Process each season
    for season in seasons:
        db_filename = f"moneyline_{season%100:02d}.db"
        db_path = os.path.join(SCRAPE_DIR, db_filename)
        
        # Step 1: Scrape data
        if not args.skip_scrape:
            print(f"\n{'='*70}")
            print(f"STEP 1: SCRAPING {season}-{(season+1)%100:02d} SEASON")
            print(f"{'='*70}\n")
            
            scraper = OddsPortalScraper(headless=args.headless)
            try:
                season_games = scraper.scrapeSeasonSchedule(season)
            except RuntimeError as e:
                print(f"\n❌ Scraping {season}-{(season+1)%100:02d} aborted: {e}")
                print(f"⏭️  Skipping this season and moving on (no data was saved for it).")
                continue

            # Save to database
            save_to_database({season: season_games}, db_path)
            print(f"\n✅ Saved data to: {db_path}")
        else:
            print(f"\n⏭️  Skipping scrape, using existing database: {db_path}")
            if not os.path.exists(db_path):
                print(f"❌ Error: Database file not found: {db_path}")
                continue
        
        # Step 2: Verify scraped data
        print(f"\n{'='*70}")
        print(f"STEP 2: VERIFYING SCRAPED DATA")
        print(f"{'='*70}")
        
        verification_results = verify_scraped_data(db_path, season)
        print_verification_results(season, verification_results)

        # Step 2.5: Validate scraped opponents against the authoritative schedule
        if not args.skip_schedule_validation:
            print(f"\n{'='*70}")
            print(f"STEP 2.5: VALIDATING AGAINST AUTHORITATIVE SCHEDULE")
            print(f"{'='*70}")

            cache_dir = os.path.join(SCRAPE_DIR, '.bbref_cache', str(season))
            schedule_comparisons = validate_scraped_data_against_schedule(db_path, season, cache_dir=cache_dir)
            print_schedule_validation_results(season, schedule_comparisons)

        # Step 3: Prompt for migration
        print(f"{'='*70}")
        print(f"STEP 3: MIGRATION TO VERCEL POSTGRES")
        print(f"{'='*70}\n")
        
        response = input(f"Ready to migrate {season}-{(season+1)%100:02d} data to Vercel Postgres? (Y/n): ").strip().upper()
        
        if response in ['Y', 'YES', '']:
            print(f"\n🚀 Starting migration for {season}-{(season+1)%100:02d}...\n")
            
            try:
                inserted = migrate_season_to_postgres(db_path, season)
                print(f"\n✅ Migration complete: {inserted} games inserted")
                
                # Track this season for frontend update
                migrated_seasons.append(season)
                
                # Clean up temporary SQLite database after successful migration
                os.remove(db_path)
                print(f"🗑️  Cleaned up temporary database: {db_path}")
            except Exception as e:
                print(f"\n❌ Migration failed: {e}")
                continue
        else:
            print(f"\n⏭️  Skipping migration for {season}-{(season+1)%100:02d}")
            continue
    
    # Step 4: Update frontend with new seasons
    if migrated_seasons:
        print(f"\n{'='*70}")
        print(f"STEP 4: UPDATING FRONTEND SEASONS LIST")
        print(f"{'='*70}\n")
        
        seasons_added = update_seasons_list(migrated_seasons)
        
        if seasons_added:
            season_strs = ', '.join(f"{s}-{(s+1)%100:02d}" for s in migrated_seasons)
            print(f"📝 Added {season_strs} to frontend seasons list")
            
            if commit_and_push_changes(migrated_seasons):
                print(f"✅ Changes committed and pushed to git")
            else:
                print(f"⚠️  Git operation failed (changes may need manual commit)")
        else:
            print(f"ℹ️  Seasons already exist in frontend, no update needed")
    
    # Step 5: Final verification
    print(f"\n{'='*70}")
    print(f"STEP 5: FINAL DATABASE VERIFICATION")
    print(f"{'='*70}")
    
    postgres_results = verify_postgres_migration()
    print_postgres_verification(postgres_results)
    
    print(f"{'='*70}")
    print(f"✅ PIPELINE COMPLETE!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
