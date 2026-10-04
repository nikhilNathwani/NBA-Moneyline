"""
Parses basketball-reference season-schedule HTML into a team's ordered list
of true regular-season games (date, opponent, home/away, result), with
in-season-tournament (IST) knockout games and play-in games excluded.

Pure parsing/filtering logic, no network access, so it can be unit tested
against saved HTML fixtures.
"""

from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup

IST_GROUP_STAGE_GAME_COUNT = 4  # every team plays exactly 4 IST group-stage games
# basketball-reference's label for IST games: "In-Season Tournament" in its
# first season (2023-24), "NBA Cup" since
IST_NOTE_TEXTS = {"In-Season Tournament", "NBA Cup"}
# Play-in games are listed in the regular-season table after a team's last
# regular-season game - numbered 73-75 in the COVID seasons, 83-84 in 82-game
# ones - so they're identified by this label, not by game number
PLAY_IN_NOTE_TEXT = "Play-In Game"


# basketball-reference's game_location values
HOME, AWAY, NEUTRAL = "", "@", "N"


@dataclass
class ScheduleGame:
    game_number: int
    date: str
    opponent: str
    note: str
    location: str = HOME  # HOME, AWAY or NEUTRAL (both teams "N" - e.g. games abroad)
    result: str = ""      # "W" or "L", from this team's side


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
            location=row.find("td", {"data-stat": "game_location"}).get_text(strip=True),
            result=row.find("td", {"data-stat": "game_result"}).get_text(strip=True),
        ))
    return games


def getTrueRegularSeasonOpponents(games: List[ScheduleGame]) -> List[str]:
    """The ordered opponent list for a team's true regular season (see below)."""
    return [game.opponent for game in getTrueRegularSeasonGames(games)]


def getTrueRegularSeasonGames(games: List[ScheduleGame]) -> List[ScheduleGame]:
    """
    Return a team's "true" regular-season games in order, excluding play-in
    games and IST knockout-round games.

    IST knockout games are detected dynamically rather than by hardcoded
    date: every team plays exactly IST_GROUP_STAGE_GAME_COUNT group-stage
    games (tagged with an IST_NOTE_TEXTS label) early in the season; any
    additional IST-tagged games beyond that count are knockout-round games
    (quarterfinal/semifinal), which we deliberately don't scrape from
    OddsPortal. This works for any season without needing this season's
    specific knockout dates hardcoded.
    """
    ist_games_seen = 0
    true_games = []
    for game in games:
        if game.note == PLAY_IN_NOTE_TEXT:
            continue
        if game.note in IST_NOTE_TEXTS:
            ist_games_seen += 1
            if ist_games_seen > IST_GROUP_STAGE_GAME_COUNT:
                continue  # knockout-round game, excluded from our dataset
        true_games.append(game)
    return true_games
