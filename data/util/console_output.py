"""
Console output formatting utilities for the NBA Moneyline data pipeline.
"""

from typing import Dict, List

from validate.checks import TeamScheduleComparison


def print_section_header(title: str):
    """Print a bracketed section header - used for every step/result banner throughout the pipeline."""
    print(f"\n{'='*70}")
    print(title)
    print(f"{'='*70}\n")


def print_game_count_results(season: int, results: Dict):
    """Print the game-count check (Step 2)."""
    print_section_header(f"VERIFICATION RESULTS - {season}-{(season+1)%100:02d} Season")

    distribution = results['expected_distribution']
    if distribution is None:
        print(f"ℹ️  Total team-game rows scraped: {results['total_games']} (2 per game)")
        print(f"ℹ️  No fixed game-count expectation for this season (see util/constants.py) - "
              f"the schedule validation in Step 2.5 is the check.\n")
    else:
        status = "✅" if results['total_games_ok'] else "❌"
        print(f"{status} Total team-game rows scraped: {results['total_games']} "
              f"(expected {results['expected_total']}; 2 per game)\n")

    print(f"📋 Games Per Team:")
    print(f"{'─'*70}")
    for team, count in results['team_counts']:
        flag = "" if distribution is None or count in distribution else "  ⚠️  unexpected count"
        print(f"  {team:.<50} {count:>3} games{flag}")
    print(f"{'─'*70}\n")

    if distribution is None:
        return
    if results['distribution_ok']:
        print(f"✅ Per-team distribution matches expectations: "
              f"{', '.join(f'{n} teams @ {c}' for c, n in sorted(distribution.items(), reverse=True))}\n")
    else:
        print(f"❌ Per-team distribution does NOT match expectations:")
        for expected_count, (expected_teams, actual_teams) in results['distribution_mismatch'].items():
            print(f"    Expected {expected_teams} teams with {expected_count} games, found {actual_teams}")
        for team, count in results['unexpected_teams']:
            expected_counts = '/'.join(str(c) for c in sorted(distribution, reverse=True))
            print(f"    {team}: {count} games (not {expected_counts} at all)")
        print()


def print_schedule_validation_results(season: int, comparisons: List[TeamScheduleComparison]):
    """Print the per-team comparison against basketball-reference's authoritative schedule."""
    print_section_header(f"SCHEDULE VALIDATION vs. basketball-reference - {season}-{(season+1)%100:02d} Season")

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
    print_section_header("POSTGRES DATABASE VERIFICATION")
    
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
