"""
Tests for extract.schedules.parser using saved HTML fixtures
(no network access) covering the cases that matter for our IST/play-in
exclusion logic: an unaffected team, an IST quarterfinal-round loser, an IST
semifinalist, and a team that also played in the play-in tournament - plus
older seasons whose format differs: the 2019-20 COVID bubble, the 72-game
2020-21 season (play-in games numbered below 82), and 2023-24 (IST labeled
"In-Season Tournament" rather than "NBA Cup").

The unlabeled fixtures are from 2025-26.
"""

import os

from extract.schedules.parser import parseScheduleTable, getTrueRegularSeasonOpponents

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


def test_bubble_season_playin_game_is_excluded():
    """2019-20: the play-in was game 74 for Memphis - inside 1..82, so only its label marks it."""
    games, true_opponents = _load_true_opponents("MEM_2019-20_bubble_playin_73.html")
    assert len(games) == 74
    assert len(true_opponents) == 73


def test_shortened_season_playin_games_are_excluded():
    """2020-21: a 72-game season, with the play-in as games 73-74."""
    games, true_opponents = _load_true_opponents("GSW_2020-21_playin_72.html")
    assert len(games) == 74
    assert len(true_opponents) == 72


def test_in_season_tournament_label_is_recognized():
    """2023-24 labels IST games "In-Season Tournament"; LAL won it (2 knockout
    games excluded) and also played in the play-in (1 more excluded)."""
    games, true_opponents = _load_true_opponents("LAL_2023-24_ist_semifinalist_playin_80.html")
    assert len(games) == 83
    assert len(true_opponents) == 80
