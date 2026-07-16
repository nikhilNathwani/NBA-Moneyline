"""
Tests for the pure URL-construction/matching helpers in oddsportal.helpers.

OddsPortal only archives a season under its own URL once a newer season has
started; the most recently completed season is only reachable via the
generic "current results" page until then. These functions are how the
scraper detects which case applies (see _resolveSeasonUrlBuilder in
oddsportal_scraper.py) instead of hardcoding an assumption that breaks the
moment a new season begins.
"""

from oddsportal.helpers import makeSeasonSpecificUrl, makeCurrentSeasonUrl, urlMatchesRequestedSeason


def test_season_specific_url_contains_season_and_page():
    url = makeSeasonSpecificUrl(2024, 3)
    assert "nba-2024-2025" in url
    assert "/page/3/" in url


def test_current_season_url_has_no_season_segment():
    url = makeCurrentSeasonUrl(3)
    assert "nba-" not in url  # no "nba-YYYY-YYYY" archive segment
    assert "/page/3/" in url


def test_url_matches_requested_season_when_not_redirected():
    url = makeSeasonSpecificUrl(2024, 1)
    assert urlMatchesRequestedSeason(url, 2024)


def test_url_does_not_match_after_redirect_to_generic_page():
    redirected_url = "https://www.oddsportal.com/basketball/usa/nba/#/page/1/"
    assert not urlMatchesRequestedSeason(redirected_url, 2025)


def test_url_does_not_match_a_different_season():
    url = makeSeasonSpecificUrl(2024, 1)
    assert not urlMatchesRequestedSeason(url, 2023)
