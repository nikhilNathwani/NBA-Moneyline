"""
Matches the scraped games to basketball-reference's schedule, turning the
scraper's two rows per game (one per team, in OddsPortal's listing order)
into one record per real game with its date and home/away teams - the shape
of the production `games` table.

Each real game on basketball-reference (date, both teams, winner) is matched
to the two scraped rows that represent it: one from each team, naming the
other as opponent, with the right winner, mirrored odds (each side's odds to
win are the other side's odds to lose), within MAX_POSITION_GAP places of
the game's position in that team's real schedule, and - when the row has
OddsPortal's date - within MAX_DATE_GAP of the real date (OddsPortal's
dates can run a day ahead). The date check is what keeps repeat matchups a
few days apart distinct when a team's list has a gap. Every scraped row
must be used exactly once.

Three passes:
1. Games whose rows sit at exactly the right position for both teams - the
   usual case, where everything agrees.
2. The rest by elimination: repeatedly assign any game left with exactly one
   possible pair of rows. This handles games OddsPortal lists out of date
   order, and a team's later games shifting when one game is missing.
3. When elimination stalls, a game with exactly one closest-dated candidate
   pair gets it (e.g. the same teams on consecutive days), then elimination
   resumes.
Anything still ambiguous or unmatched raises MatchError rather than guessing.

Pure logic, no network access.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List

from util.records import TeamGame, GameRecord
from extract.basketball_reference.parser import AWAY, NEUTRAL, ScheduleGame

MAX_POSITION_GAP = 8
MAX_DATE_GAP = timedelta(days=1)


@dataclass
class MatchResult:
    records: List[GameRecord]   # one per real game, sorted by date
    listed_out_of_order: int    # games OddsPortal listed away from their real date order


class MatchError(Exception):
    pass


def _real_games(schedules: Dict[str, List[ScheduleGame]]) -> List[dict]:
    """Each real game once, with both teams' positions in their own schedules."""
    position = {team: {(g.date, g.opponent): n for n, g in enumerate(games, 1)}
                for team, games in schedules.items()}
    games, seen = [], set()
    for team, team_schedule in schedules.items():
        for n, g in enumerate(team_schedule, 1):
            key = (g.date, frozenset((team, g.opponent)))
            if key in seen:
                continue
            seen.add(key)
            if g.opponent not in position or (g.date, team) not in position[g.opponent]:
                raise MatchError(f"{team} vs {g.opponent} on {g.date} is missing from "
                                 f"{g.opponent}'s basketball-reference schedule")
            team_won = g.result == "W"
            if g.location == AWAY:
                home, away, home_won = g.opponent, team, not team_won
            elif g.location == NEUTRAL:
                home, away = sorted((team, g.opponent))
                home_won = team_won if home == team else not team_won
            else:
                home, away, home_won = team, g.opponent, team_won
            games.append(dict(date=g.date, date_value=datetime.strptime(g.date, "%a, %b %d, %Y").date(),
                              home=home, away=away, neutral=g.location == NEUTRAL,
                              home_won=home_won,
                              pos={team: n, g.opponent: position[g.opponent][(g.date, team)]}))
    return games


def _candidate_pairs(game: dict, rows: Dict[str, List[TeamGame]]) -> set:
    """Pairs of (home row index, away row index) that could represent this game."""
    home, away = game["home"], game["away"]

    def near(team, opponent, won):
        return [i for i, r in enumerate(rows.get(team, []))
                if r.opponent == opponent and r.outcome == won
                and abs(r.game_number - game["pos"][team]) <= MAX_POSITION_GAP
                and (r.listed_date is None or abs(r.listed_date - game["date_value"]) <= MAX_DATE_GAP)]

    home_rows = near(home, away, game["home_won"])
    away_rows = near(away, home, not game["home_won"])
    return {(h, a) for h in home_rows for a in away_rows
            if rows[home][h].win_odds == rows[away][a].lose_odds
            and rows[home][h].lose_odds == rows[away][a].win_odds}


def match_to_schedule(team_games: Dict[str, List[TeamGame]],
                      schedules: Dict[str, List[ScheduleGame]]) -> MatchResult:
    """
    Args:
        team_games: scraped games straight from the scraper's output
            ({team: games}, game_number = position in OddsPortal's order)
        schedules: basketball-reference's true schedules (extract.basketball_reference.scraper.scrape_season)

    Returns one GameRecord per real game, plus how many games needed pass 2
    (listed out of date order on OddsPortal). Raises MatchError
    if any game can't be matched to exactly one pair of scraped rows, or any
    scraped row is left over.
    """
    games = _real_games(schedules)
    candidates = [_candidate_pairs(g, team_games) for g in games]
    assigned: Dict[int, tuple] = {}
    used = set()  # (team, row index)

    def assign(i, pair):
        assigned[i] = pair
        used.update({(games[i]["home"], pair[0]), (games[i]["away"], pair[1])})

    def free(i, pair):
        return (games[i]["home"], pair[0]) not in used and (games[i]["away"], pair[1]) not in used

    # Pass 1: both rows exactly where the real schedule says
    for i, g in enumerate(games):
        for pair in candidates[i]:
            h_row, a_row = team_games[g["home"]][pair[0]], team_games[g["away"]][pair[1]]
            if h_row.game_number == g["pos"][g["home"]] and a_row.game_number == g["pos"][g["away"]] and free(i, pair):
                assign(i, pair)
                break

    in_place = len(assigned)

    def date_gap(i, pair):
        """Total days between the pair's OddsPortal dates and the real date."""
        g = games[i]
        rows_ = (team_games[g["home"]][pair[0]], team_games[g["away"]][pair[1]])
        return sum(abs((r.listed_date - g["date_value"]).days) for r in rows_ if r.listed_date)

    # Pass 2: elimination - any game with exactly one possible pair left gets
    # it. Pass 3 (only when that stalls): a game whose candidates include
    # exactly one closest-dated pair gets that pair - e.g. the same two teams
    # on consecutive days, where both pairs fit within MAX_DATE_GAP - then
    # elimination resumes.
    while True:
        progress = False
        for i in range(len(games)):
            if i in assigned:
                continue
            remaining = [p for p in candidates[i] if free(i, p)]
            if len(remaining) == 1:
                assign(i, remaining[0])
                progress = True
        if progress:
            continue
        for i in range(len(games)):
            if i in assigned:
                continue
            remaining = sorted((date_gap(i, p), p) for p in candidates[i] if free(i, p))
            if len(remaining) > 1 and remaining[0][0] < remaining[1][0]:
                assign(i, remaining[0][1])
                progress = True
                break
        if not progress:
            break

    unmatched = [games[i] for i in range(len(games)) if i not in assigned]
    if unmatched:
        shown = ", ".join(f"{g['away']} at {g['home']} on {g['date']}" for g in unmatched[:5])
        raise MatchError(f"{len(unmatched)} game(s) couldn't be matched to exactly one pair of "
                         f"scraped rows: {shown}{' ...' if len(unmatched) > 5 else ''}")
    leftover = sum(len(r) for r in team_games.values()) - len(used)
    if leftover:
        raise MatchError(f"{leftover} scraped row(s) don't belong to any game on basketball-reference's schedule")

    records = []
    for i, (h, a) in assigned.items():
        g = games[i]
        records.append(GameRecord(
            game_date=datetime.strptime(g["date"], "%a, %b %d, %Y").date(),
            home=g["home"], away=g["away"], neutral_site=g["neutral"], home_won=g["home_won"],
            home_odds=team_games[g["home"]][h].win_odds, away_odds=team_games[g["away"]][a].win_odds,
        ))
    return MatchResult(records=sorted(records, key=lambda r: (r.game_date, r.home)),
                       listed_out_of_order=len(games) - in_place)

