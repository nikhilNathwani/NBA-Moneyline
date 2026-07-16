"""
Console output formatting utilities for the NBA Moneyline data pipeline.
"""

from typing import Dict, List

from util.constants import TOTAL_EXPECTED_GAMES, EXPECTED_GAME_COUNT_DISTRIBUTION
from scrape.verification import TeamScheduleComparison


def print_verification_results(season: int, results: Dict):
    """Print scraped data verification results."""
    print(f"\n{'='*70}")
    print(f"VERIFICATION RESULTS - {season}-{(season+1)%100:02d} Season")
    print(f"{'='*70}\n")

    total_ok = results.get('total_games_ok')
    status = "✅" if total_ok else "❌"
    print(f"{status} Total Games Scraped: {results['total_games']} (expected {TOTAL_EXPECTED_GAMES})\n")

    print(f"📋 Games Per Team:")
    print(f"{'─'*70}")
    for team, count in results['team_counts']:
        flag = "" if count in EXPECTED_GAME_COUNT_DISTRIBUTION else "  ⚠️  unexpected count"
        print(f"  {team:.<50} {count:>3} games{flag}")
    print(f"{'─'*70}\n")

    if results.get('distribution_ok'):
        print(f"✅ Per-team distribution matches expectations: "
              f"{', '.join(f'{n} teams @ {c}' for c, n in sorted(EXPECTED_GAME_COUNT_DISTRIBUTION.items(), reverse=True))}\n")
    else:
        print(f"❌ Per-team distribution does NOT match expectations:")
        for expected_count, (expected_teams, actual_teams) in results.get('distribution_mismatch', {}).items():
            print(f"    Expected {expected_teams} teams with {expected_count} games, found {actual_teams}")
        for team, count in results.get('unexpected_teams', []):
            print(f"    {team}: {count} games (not 82/81/80 at all)")
        print()


def print_schedule_validation_results(season: int, comparisons: List[TeamScheduleComparison]):
    """Print the per-team comparison against basketball-reference's authoritative schedule."""
    print(f"\n{'='*70}")
    print(f"SCHEDULE VALIDATION vs. basketball-reference - {season}-{(season+1)%100:02d} Season")
    print(f"{'='*70}\n")

    mismatched = [c for c in comparisons if not c.ok]

    for c in sorted(comparisons, key=lambda c: c.team):
        status = "✅" if c.ok else "❌"
        print(f"{status} {c.team:.<50} true={c.true_game_count:>3}  scraped={c.scraped_game_count:>3}")
        if not c.ok:
            for opponent, count in c.missing_opponents.items():
                print(f"      missing: {count}x vs {opponent}")
            for opponent, count in c.extra_opponents.items():
                print(f"      extra:   {count}x vs {opponent}")

    print(f"\n{'─'*70}")
    if not mismatched:
        print(f"✅ All {len(comparisons)} teams' scraped opponents match the authoritative schedule\n")
    else:
        print(f"❌ {len(mismatched)}/{len(comparisons)} teams have opponent mismatches vs. the authoritative schedule\n")


def print_postgres_verification(results: Dict):
    """Print Postgres database verification results."""
    print(f"\n{'='*70}")
    print(f"POSTGRES DATABASE VERIFICATION")
    print(f"{'='*70}\n")
    
    if 'error' in results:
        print(f"❌ Error connecting to database: {results['error']}\n")
        return
    
    print(f"📊 Games Per Season in Database:")
    print(f"{'─'*70}")
    total_games = 0
    for season, count in results['season_counts']:
        print(f"  {season}-{(season+1)%100:02d}:{'.'*(50-len(f'{season}-{(season+1)%100:02d}:'))} {count:>5} games")
        total_games += count
    print(f"{'─'*70}")
    print(f"  TOTAL:{'.'*55} {total_games:>5} games")
    print(f"{'─'*70}\n")
