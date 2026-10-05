"""
Tests for the pure URL functions in extract.oddsportal.parser.

OddsPortal only archives a season under its own URL once a newer season has
started; the most recently completed season is only reachable via the
generic "current results" page until then. These functions are how the
scraper detects which case applies (see _resolve_season_url in scraper.py)
instead of hardcoding an assumption that breaks the moment a new season
begins. The NBA Cup's knockout games live under a separate competition
whose archive names vary by edition.
"""

from extract.oddsportal.parser import (
    make_season_specific_url, make_current_season_url, url_matches_requested_season, make_cup_url_candidates,
)


def test_season_specific_url_contains_season():
    assert make_season_specific_url(2024).endswith("/basketball/usa/nba-2024-2025/results/")


def test_current_season_url_is_season_agnostic():
    assert make_current_season_url().endswith("/basketball/usa/nba/results/")


def test_url_matches_requested_season():
    assert url_matches_requested_season(make_season_specific_url(2024), 2024)


def test_redirected_generic_url_does_not_match():
    assert not url_matches_requested_season(make_current_season_url(), 2024)


def test_cup_url_candidates_cover_each_known_archive_name():
    candidates = make_cup_url_candidates(2023)
    assert any("nba-in-season-tournament-2023" in u for u in candidates)  # 2023-24's archive
    assert any("nba-cup-2023" in u for u in candidates)                   # 2024-25's naming
    assert candidates[-1].endswith("/nba-cup/results/")                   # latest edition, tried last
