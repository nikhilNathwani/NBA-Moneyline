"""
Tests for the pure comparison logic in utils.schedule_validation.

These use synthetic opponent lists (no network, no fixtures) since
compare_opponent_multisets is a pure function.
"""

from utils.schedule_validation import compare_opponent_multisets


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
