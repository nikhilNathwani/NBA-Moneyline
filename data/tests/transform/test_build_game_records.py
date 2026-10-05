"""
Tests for transform.build_game_records using a small synthetic season (no network):
four teams, three game days, built both as basketball-reference schedules
and as scraper output.
"""

import datetime

import pytest

from util.records import TeamGame
from transform.build_game_records import MatchError, match_to_schedule
from extract.basketball_reference.parser import AWAY, HOME, NEUTRAL, ScheduleGame

# (date, home, away, home_won, home_odds, away_odds, neutral)
SEASON = [
    ("Mon, Nov 3, 2025", "A", "B", True, -150, 130, False),
    ("Mon, Nov 3, 2025", "C", "D", False, -120, 100, False),
    ("Wed, Nov 5, 2025", "A", "C", False, 110, -130, False),
    ("Wed, Nov 5, 2025", "B", "D", True, -200, 170, False),
    ("Fri, Nov 7, 2025", "D", "A", False, 140, -160, False),
    ("Fri, Nov 7, 2025", "B", "C", False, 120, -140, False),
]


def _schedules(games):
    """basketball-reference's view: each team's games in date order."""
    schedules = {}
    for date, home, away, home_won, _, _, neutral in games:
        for team, opponent, won, location in ((home, away, home_won, NEUTRAL if neutral else HOME),
                                              (away, home, not home_won, NEUTRAL if neutral else AWAY)):
            team_games = schedules.setdefault(team, [])
            team_games.append(ScheduleGame(len(team_games) + 1, date, opponent, "", location, "W" if won else "L"))
    return schedules


def _scraped(games, order=None):
    """The scraper's view: two rows per game; `order` optionally overrides a
    team's row order ({team: [indexes into that team's games, in listed order]})."""
    rows = {}
    for date, home, away, home_won, home_odds, away_odds, _ in games:
        rows.setdefault(home, []).append(TeamGame(home, away, home_won, home_odds, away_odds, 2025))
        rows.setdefault(away, []).append(TeamGame(away, home, not home_won, away_odds, home_odds, 2025))
    for team, indexes in (order or {}).items():
        rows[team] = [rows[team][i] for i in indexes]
    for team_rows in rows.values():
        for n, game in enumerate(team_rows, 1):
            game.game_number = n
    return rows


def _summary(result):
    return [(r.game_date.isoformat(), r.home, r.away, r.home_won, r.home_odds, r.away_odds, r.neutral_site)
            for r in result.records]


EXPECTED = [
    ("2025-11-03", "A", "B", True, -150, 130, False),
    ("2025-11-03", "C", "D", False, -120, 100, False),
    ("2025-11-05", "A", "C", False, 110, -130, False),
    ("2025-11-05", "B", "D", True, -200, 170, False),
    ("2025-11-07", "B", "C", False, 120, -140, False),
    ("2025-11-07", "D", "A", False, 140, -160, False),
]


def test_games_in_order_all_match_with_dates_and_home_teams():
    result = match_to_schedule(_scraped(SEASON), _schedules(SEASON))
    assert _summary(result) == EXPECTED
    assert result.listed_out_of_order == 0


def test_game_listed_out_of_date_order_still_lands_on_its_real_date():
    # Like 2025-26 on OddsPortal: A vs B (really their first game) listed as both teams' last
    scraped = _scraped(SEASON, order={"A": [1, 2, 0], "B": [1, 2, 0]})
    result = match_to_schedule(scraped, _schedules(SEASON))
    assert _summary(result) == EXPECTED
    assert result.listed_out_of_order > 0


def test_neutral_site_game_gets_alphabetical_home_and_correct_winner():
    season = [("Sat, Nov 1, 2025", "D", "A", True, -110, -110, True)]  # D won, abroad
    result = match_to_schedule(_scraped(season), _schedules(season))
    record = result.records[0]
    assert (record.home, record.away, record.neutral_site) == ("A", "D", True)
    assert record.home_won is False  # "home" A lost
    assert record.game_date == datetime.date(2025, 11, 1)


def test_missing_scraped_game_raises():
    scraped = _scraped(SEASON)
    scraped["A"] = [g for g in scraped["A"] if g.opponent != "C"]
    scraped["C"] = [g for g in scraped["C"] if g.opponent != "A"]
    with pytest.raises(MatchError, match="couldn't be matched"):
        match_to_schedule(scraped, _schedules(SEASON))


def test_extra_scraped_row_raises():
    scraped = _scraped(SEASON)
    scraped["A"].append(TeamGame("A", "B", True, -150, 130, 2025, 4))
    scraped["B"].append(TeamGame("B", "A", False, 130, -150, 2025, 4))
    with pytest.raises(MatchError, match="don't belong to any game"):
        match_to_schedule(scraped, _schedules(SEASON))


def test_mismatched_odds_raise_instead_of_guessing():
    scraped = _scraped(SEASON)
    scraped["B"][0].lose_odds = -999  # B's row no longer mirrors A's
    with pytest.raises(MatchError):
        match_to_schedule(scraped, _schedules(SEASON))


def test_team_missing_a_game_still_matches_its_other_games_by_date():
    # A and B play twice, three days apart; A's first game (vs B) has no row,
    # shifting A's later rows by one position
    season = [("Mon, Nov 3, 2025", "A", "B", True, -150, 130, False),
              ("Wed, Nov 5, 2025", "C", "A", False, 110, -130, False),
              ("Thu, Nov 6, 2025", "A", "B", False, 120, -140, False)]
    scraped = _scraped(season)
    for team in ("A", "B"):
        scraped[team] = [g for g in scraped[team] if not (g.opponent in ("A", "B") and g.win_odds in (-150, 130))]
        for n, g in enumerate(scraped[team], 1):
            g.game_number = n
    for team, team_rows in scraped.items():
        for g in team_rows:
            g.listed_date = {("A", "C"): 5, ("C", "A"): 5}.get((team, g.opponent), 6)
            g.listed_date = __import__("datetime").date(2025, 11, g.listed_date)
    with pytest.raises(MatchError, match="1 game"):  # only the truly missing game fails
        match_to_schedule(scraped, _schedules(season))


def test_same_teams_on_consecutive_days_are_told_apart_by_date():
    import datetime
    season = [("Thu, Feb 19, 2026", "W", "I", True, -150, 130, False),
              ("Fri, Feb 20, 2026", "W", "I", True, -160, 140, False)]
    scraped = _scraped(season)
    for team_rows in scraped.values():
        for g, day in zip(team_rows, (19, 20)):
            g.listed_date = datetime.date(2026, 2, day)
    # Shift positions so pass 1 (exact position) can't settle it
    for g in scraped["I"]:
        g.game_number += 1
    result = match_to_schedule(scraped, _schedules(season))
    assert [(r.game_date.day, r.home_odds) for r in result.records] == [(19, -150), (20, -160)]
