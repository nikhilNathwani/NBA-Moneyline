"""
Parses basketball-reference season-schedule HTML into an ordered list of
regular-season opponents, with in-season-tournament (IST) knockout games
and play-in games excluded.

Pure parsing/filtering logic, no network access, so it can be unit tested
against saved HTML fixtures.
"""

from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup

REGULAR_SEASON_GAME_COUNT = 82
IST_GROUP_STAGE_GAME_COUNT = 4  # every team plays exactly 4 IST group-stage games
IST_NOTE_TEXT = "NBA Cup"


@dataclass
class ScheduleGame:
    game_number: int
    date: str
    opponent: str
    note: str


def parseScheduleTable(html: str) -> List[ScheduleGame]:
    """Parse every game row out of a team's basketball-reference schedule page."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id="games")
    if table is None:
        raise ValueError("Could not find the games table (id='games') in the schedule page")

    rows = table.find("tbody").find_all("tr")
    games = []
    for row in rows:
        game_number_cell = row.find("th")
        if game_number_cell is None or not game_number_cell.get_text(strip=True).isdigit():
            continue  # repeated header row, not a game row
        cells = row.find_all("td")
        games.append(ScheduleGame(
            game_number=int(game_number_cell.get_text(strip=True)),
            date=cells[0].get_text(strip=True),
            opponent=cells[5].get_text(strip=True),
            note=cells[-1].get_text(strip=True),
        ))
    return games


def getTrueRegularSeasonOpponents(games: List[ScheduleGame]) -> List[str]:
    """
    Return the ordered opponent list for a team's "true" regular season,
    excluding play-in games and IST knockout-round games.

    IST knockout games are detected dynamically rather than by hardcoded
    date: every team plays exactly IST_GROUP_STAGE_GAME_COUNT group-stage
    games (tagged with IST_NOTE_TEXT) early in the season; any additional
    IST_NOTE_TEXT-tagged games beyond that count are knockout-round games
    (quarterfinal/semifinal), which we deliberately don't scrape from
    OddsPortal. This works for any season without needing this season's
    specific knockout dates hardcoded.
    """
    regular_season_games = [g for g in games if g.game_number <= REGULAR_SEASON_GAME_COUNT]

    ist_games_seen = 0
    true_opponents = []
    for game in regular_season_games:
        if game.note == IST_NOTE_TEXT:
            ist_games_seen += 1
            if ist_games_seen > IST_GROUP_STAGE_GAME_COUNT:
                continue  # knockout-round game, excluded from our dataset
        true_opponents.append(game.opponent)
    return true_opponents
