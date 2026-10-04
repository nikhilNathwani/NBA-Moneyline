"""
Tests for the pure logic in validate.verification: the opponent comparison and
the season-aware game-count check.

These use synthetic data (no network, no fixtures) since both are pure
functions.
"""

from validate.verification import compare_opponent_multisets, verify_scraped_data
from util.game import Game


def test_identical_sequences_match():
    true_opponents = ["Boston Celtics", "Miami Heat", "New York Knicks"]
    scraped_opponents = ["Boston Celtics", "Miami Heat", "New York Knicks"]
    diff = compare_opponent_multisets(true_opponents, scraped_opponents)
    assert not diff["missing"]
    assert not diff["extra"]


def test_reordering_alone_is_not_a_mismatch():
    """A legitimate game postponement/reschedule shifts order, not the opponent set."""
    true_opponents = ["Boston Celtics", "Miami Heat", "New York Knicks", "Orlando Magic"]
    scraped_opponents = ["Miami Heat", "New York Knicks", "Orlando Magic", "Boston Celtics"]
    diff = compare_opponent_multisets(true_opponents, scraped_opponents)
    assert not diff["missing"]
    assert not diff["extra"]


def test_missing_game_is_detected():
    true_opponents = ["Boston Celtics", "Miami Heat", "New York Knicks"]
    scraped_opponents = ["Boston Celtics", "Miami Heat"]  # New York Knicks never scraped
    diff = compare_opponent_multisets(true_opponents, scraped_opponents)
    assert diff["missing"] == {"New York Knicks": 1}
    assert not diff["extra"]


def test_duplicate_scrape_is_detected_as_extra():
    true_opponents = ["Boston Celtics", "Miami Heat"]
    scraped_opponents = ["Boston Celtics", "Miami Heat", "Miami Heat"]  # double-scraped
    diff = compare_opponent_multisets(true_opponents, scraped_opponents)
    assert not diff["missing"]
    assert diff["extra"] == {"Miami Heat": 1}


def test_legitimate_rematch_with_repeated_opponent_is_not_flagged():
    """Two teams can play each other multiple times in a season; repeats
    in both lists at the same count should not be flagged at all."""
    true_opponents = ["Miami Heat", "Orlando Magic", "Miami Heat", "Miami Heat"]
    scraped_opponents = ["Orlando Magic", "Miami Heat", "Miami Heat", "Miami Heat"]
    diff = compare_opponent_multisets(true_opponents, scraped_opponents)
    assert not diff["missing"]
    assert not diff["extra"]


def _season_with_counts(counts):
    """Scraped-data stand-in: {team: [games]} with the given per-team counts."""
    return {f"Team {i:02d}": [Game(f"Team {i:02d}", "X", True, -110, -110, 2000)] * n
            for i, n in enumerate(counts)}


def test_normal_season_expects_82_each():
    results = verify_scraped_data(_season_with_counts([82] * 30), 2016)
    assert results['total_games_ok'] and results['distribution_ok']
    assert results['expected_total'] == 2460


def test_shortened_season_expects_72_each():
    assert verify_scraped_data(_season_with_counts([72] * 30), 2020)['distribution_ok']
    # The same data would be badly short in a normal season
    assert not verify_scraped_data(_season_with_counts([72] * 30), 2021)['distribution_ok']


def test_ist_season_expects_82_81_80_distribution():
    counts = [82] * 22 + [81] * 4 + [80] * 4
    results = verify_scraped_data(_season_with_counts(counts), 2023)
    assert results['total_games_ok'] and results['distribution_ok']
    assert results['expected_total'] == 2448


def test_wrong_distribution_with_right_counts_is_caught():
    counts = [82] * 21 + [81] * 5 + [80] * 4  # every count is a valid one, but 5 teams at 81
    results = verify_scraped_data(_season_with_counts(counts), 2024)
    assert not results['distribution_ok']
    assert results['distribution_mismatch'] == {82: (22, 21), 81: (4, 5)}


def test_bubble_season_count_check_is_not_applicable():
    """2019-20 has no fixed pattern: None means "doesn't apply", not "passed"."""
    results = verify_scraped_data(_season_with_counts([64, 75] + [72] * 28), 2019)
    assert results['expected_distribution'] is None
    assert results['distribution_ok'] is None
    assert results['total_games_ok'] is None
