"""
Tests for extract.oddsportal.parser against saved pages from OddsPortal's
redesigned site (trimmed to the results list; saved 2026-10-04), plus
synthetic row text for the edge cases - no network, no Selenium.

- cup_2023-24.html: the 2023-24 NBA Cup page - six knockout games, the final
  (under "- Play Offs"), and the pinned game (here a repeat of a quarterfinal).
- results_2023-24_page2.html: page 2 of 2023-24's NBA results - playoff
  games, then the last regular-season day, with the pinned game on top.
"""

import datetime
import os

import pytest

from extract.oddsportal.parser import (
    parse_results_page, parse_row_text, is_regular_season, get_last_page_num, build_team_games,
    rows_fall_in_season, ResultRow, parse_game_page_odds, american_to_decimal, decimal_to_american,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _page(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


# --- whole pages ---

def test_rows_carry_their_oddsportal_game_id():
    rows = parse_results_page(_page("cup_2023-24.html"))
    assert all(r.event_id and "/" not in r.event_id for r in rows)
    assert len({r.event_id for r in rows}) == len(rows)


def test_cup_page_rows_have_dates_stages_teams_scores_and_american_odds():
    rows = parse_results_page(_page("cup_2023-24.html"))
    final = rows[0]
    assert (final.home, final.away, final.stage) == ("Los Angeles Lakers", "Indiana Pacers", "Play Offs")
    assert (final.home_score, final.away_score, final.home_odds, final.away_odds) == (123, 109, -169, 150)
    assert all(isinstance(r.listed_date, datetime.date) for r in rows)


def test_cup_final_is_excluded_and_knockouts_kept():
    rows = parse_results_page(_page("cup_2023-24.html"))
    knockouts = {(r.home, r.away) for r in rows if is_regular_season(r)}
    assert len(knockouts) == 6  # 4 quarterfinals + 2 semifinals; the final doesn't count
    assert ("Los Angeles Lakers", "Indiana Pacers") not in knockouts


def test_results_page_keeps_only_regular_season_games():
    rows = parse_results_page(_page("results_2023-24_page2.html"))
    regular = [r for r in rows if is_regular_season(r)]
    assert regular and all(r.listed_date == datetime.date(2024, 4, 14) for r in regular)
    assert any(r.stage == "Play Offs" for r in rows)


def test_pinned_game_is_skipped():
    """Each page pins one game from elsewhere; its link carries no game id."""
    cup = parse_results_page(_page("cup_2023-24.html"))
    assert len(cup) == 7  # 8 links, one of them the pinned repeat
    results = parse_results_page(_page("results_2023-24_page2.html"))
    assert len(results) == 50
    assert all(r.listed_date is not None for r in results)  # the undated pinned row is gone


def test_last_page_number_comes_from_the_page_buttons():
    assert get_last_page_num(_page("results_2023-24_page2.html")) == 28
    assert get_last_page_num(_page("cup_2023-24.html")) == 1


def test_rows_fall_in_season():
    rows = parse_results_page(_page("cup_2023-24.html"))
    assert rows_fall_in_season(rows, 2023)
    assert not rows_fall_in_season(rows, 2024)


# --- single rows ---

def test_overtime_row():
    row = parse_row_text("After OT|AOT|120|New York Knicks|-|Chicago Bulls|119|-833|+575".split("|"))
    assert row == dict(home="New York Knicks", away="Chicago Bulls", home_score=120, away_score=119,
                       home_odds=-833, away_odds=575, status="After OT")


def test_row_without_odds_or_scores():
    row = parse_row_text("Postponed|POSTP|Utah Jazz|-|Denver Nuggets|-|-".split("|"))
    assert (row["home_score"], row["away_score"], row["home_odds"], row["away_odds"]) == (None, None, None, None)


def test_decimal_odds_raise_instead_of_being_misread():
    with pytest.raises(ValueError, match="American"):
        parse_row_text("Finished|FIN|106|Boston Celtics|-|Dallas Mavericks|88|1.36|3.30".split("|"))


def test_non_game_text_is_ignored():
    assert parse_row_text(["Finished", "FIN"]) is None


# --- rows -> per-team games ---

def _row(day, home, away, home_score, away_score, home_odds=-150, away_odds=130, stage="", event_id=None):
    return ResultRow(datetime.date(2023, 12, day), stage, home, away, home_score, away_score,
                     home_odds, away_odds, "Finished", event_id or f"{day}{home}{away}")


def test_team_games_are_dated_numbered_and_mirrored():
    # Listed newest first, like a results page
    games = build_team_games([_row(9, "A", "B", 100, 90), _row(5, "B", "A", 110, 100)], 2023)
    a = games["A"]
    assert [(g.listed_date.day, g.opponent, g.outcome, g.game_number) for g in a] == [(5, "B", False, 1), (9, "B", True, 2)]
    assert (a[1].win_odds, a[1].lose_odds) == (-150, 130)
    assert (games["B"][1].win_odds, games["B"][1].lose_odds) == (130, -150)


def test_rows_from_a_separate_page_slot_in_by_date():
    page = [_row(9, "A", "B", 100, 90), _row(3, "A", "C", 100, 90)]
    cup = [_row(6, "A", "D", 100, 90)]  # scraped separately, appended last
    games = build_team_games(page + cup, 2023)
    assert [g.opponent for g in games["A"]] == ["C", "D", "B"]


def test_repeated_game_is_kept_once_and_unplayed_or_unpriced_games_skipped():
    rows = [_row(9, "A", "B", 100, 90), _row(10, "A", "B", 100, 90, event_id="9AB"),  # pinned repeat, other date
            _row(8, "A", "C", None, None),                                    # postponed
            _row(7, "A", "D", 100, 90, home_odds=None, away_odds=None)]       # no odds
    games = build_team_games(rows, 2023)
    assert [g.opponent for g in games["A"]] == ["B"]


# --- the missing-odds fallback: a game's own page ---

# The bookmaker section of a real game page's text (Memphis v Indiana,
# 25 Oct 2025 - listed without odds on its results page)
GAME_PAGE_TEXT = """Memphis Grizzlies
128
-
Indiana Pacers
103
1X2
Home/Away
Over/Under
Bookmakers
1
2
Payout
bet365.us
CLAIM BONUS
-135
+114
-
BetMGM.us
CLAIM BONUS
-133
+110
-
My coupon
User Predictions
73%"""


def test_game_page_odds_are_averaged_across_bookmakers_in_decimal():
    assert parse_game_page_odds(GAME_PAGE_TEXT) == (-134, 112)


def test_game_page_without_bookmaker_lines_gives_none():
    assert parse_game_page_odds("Bookmakers\n1\n2\nPayout\nMy coupon") is None


def test_odds_conversions_round_trip():
    for american in (-1000, -200, -110, 100, 150, 1200):
        assert decimal_to_american(american_to_decimal(american)) == american
