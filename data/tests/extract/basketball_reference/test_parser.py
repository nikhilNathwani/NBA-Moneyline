"""
Tests for extract.basketball_reference.parser using saved HTML fixtures
(no network access) covering the cases that matter for which games count:
an unaffected team, an IST quarterfinal-round loser, an IST semifinalist (both
keep their knockout games, which count toward the 82), and a team that also
played in the play-in tournament (excluded) - plus older seasons whose format
differs: the 2019-20 COVID bubble and the 72-game 2020-21 season (play-in games
numbered below 82), and 2023-24's IST champion.

The unlabeled fixtures are from 2025-26.
"""

import os

from extract.basketball_reference.parser import parseScheduleTable, getTrueRegularSeasonOpponents

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


def test_ist_quarterfinal_loser_keeps_its_knockout_game():
    """IST quarterfinals count toward the regular season, so they're kept."""
    games, true_opponents = _load_true_opponents("TOR_ist_quarterfinal_loser.html")
    assert len(games) == 82
    assert len(true_opponents) == 82


def test_ist_semifinalist_keeps_both_knockout_games():
    games, true_opponents = _load_true_opponents("OKC_ist_semifinalist.html")
    assert len(games) == 82
    assert len(true_opponents) == 82


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


def test_ist_champion_with_playin_has_82():
    """2023-24: LAL won the IST (the final isn't listed - it doesn't count) and
    played in the play-in (excluded): 83 rows, 82 true games."""
    games, true_opponents = _load_true_opponents("LAL_2023-24_ist_semifinalist_playin.html")
    assert len(games) == 83
    assert len(true_opponents) == 82
