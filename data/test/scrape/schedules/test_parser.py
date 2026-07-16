"""
Tests for scrape.schedules.parser using saved HTML fixtures
(no network access) covering the three cases that matter for our IST/play-in
exclusion logic: an unaffected team, an IST quarterfinal-round loser, an IST
semifinalist, and a team that also played in the play-in tournament.
"""

import os

from scrape.schedules.parser import parseScheduleTable, getTrueRegularSeasonOpponents

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_true_opponents(fixture_filename):
    with open(os.path.join(FIXTURES_DIR, fixture_filename), encoding="utf-8") as f:
        html = f.read()
    games = parseScheduleTable(html)
    return games, getTrueRegularSeasonOpponents(games)


def test_unaffected_team_has_82_true_games():
    games, true_opponents = _load_true_opponents("BOS_unaffected_82.html")
    assert len(games) == 82
    assert len(true_opponents) == 82


def test_ist_quarterfinal_loser_excludes_one_knockout_game():
    games, true_opponents = _load_true_opponents("TOR_ist_quarterfinal_loser_81.html")
    assert len(games) == 82  # still 82 rows in the table...
    assert len(true_opponents) == 81  # ...but 1 is an IST knockout game we exclude


def test_ist_semifinalist_excludes_two_knockout_games():
    games, true_opponents = _load_true_opponents("OKC_ist_semifinalist_80.html")
    assert len(games) == 82
    assert len(true_opponents) == 80


def test_playin_games_are_excluded_regardless_of_ist_status():
    games, true_opponents = _load_true_opponents("GSW_playin_84.html")
    assert len(games) == 84  # table includes 2 play-in rows beyond the 82-game season
    assert len(true_opponents) == 82  # play-in games excluded, GSW wasn't IST-affected


def test_parsed_games_are_in_ascending_game_number_order():
    games, _ = _load_true_opponents("BOS_unaffected_82.html")
    game_numbers = [g.game_number for g in games]
    assert game_numbers == sorted(game_numbers)
    assert game_numbers[0] == 1
