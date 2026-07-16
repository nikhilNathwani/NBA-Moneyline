"""
Pure URL-construction and HTML-parsing functions for the OddsPortal
scraper. Everything here is parameterized purely by its arguments - no
live driver access - which is what makes it independently unit-testable
(see test_parser.py) without any Selenium setup. Anything that needs live
browser interaction lives on OddsPortalScraper itself instead (e.g. the
odds-missing fallback that used to live here before it needed a driver
reference to navigate to a game's detail page).
"""

from typing import List, Dict
from util.game import Game

# OddsPortal only gives a season its own archived results URL once a newer
# season has started; the most recently completed season is only reachable
# via the generic (season-agnostic) "current results" URL until then. Both
# URLs are needed - see resolveSeasonUrlTemplate() in oddsportal_scraper.py,
# which live-checks which one applies for the requested season rather than
# hardcoding an assumption that breaks as soon as a new season starts.

# Construct the archived, season-specific results URL for a given season and page number.
def makeSeasonSpecificUrl(seasonStartYear: int, pageNum: int) -> str:
    return f"https://www.oddsportal.com/basketball/usa/nba-{seasonStartYear}-{seasonStartYear+1}/results/#/page/{pageNum}/"

# Construct the generic "current results" URL (whatever season OddsPortal currently considers current).
def makeCurrentSeasonUrl(pageNum: int) -> str:
    return f"https://www.oddsportal.com/basketball/usa/nba/results/#/page/{pageNum}/"

# Check whether a (possibly redirected-to) URL still refers to the requested season's archive,
# i.e. whether OddsPortal accepted the season-specific URL instead of redirecting away from it.
def urlMatchesRequestedSeason(url: str, seasonStartYear: int) -> bool:
    return f"nba-{seasonStartYear}-{seasonStartYear+1}" in url

# Get the last page number for pagination.
def getLastPageNum(soup) -> int:
    pagination_links = soup.select('.pagination-link[data-number]')
    if pagination_links:
        last_link = pagination_links[-1]
        last_page_num = int(last_link.get('data-number'))
        return last_page_num
    else:
        print(f"No pagination links found, defaulting to 1 page")
        return 1

# Get the date header row for a game row (if present).
def getDateHeaderRow(gameRow):
    headerRow = gameRow.select_one('[data-testid="date-header"]')
    return headerRow

# Determine if games under this header are regular season games.
def isRegularSeason(header) -> bool:
    text = header.get_text(strip=True)
    #date header has "[date] - [gameType]" for non-reg season games
    return "-" not in text

# Fix game numbers to be in chronological order.
# (OddsPortal lists games in reverse chronological order, so I reverse & renumber them)
def reverseGameNumbers(games: Dict[str, List[Game]]):
    for team, team_games in games.items():
        # Reverse the list so it's in chronological order
        team_games.reverse()
        # Assign game numbers
        for i, game in enumerate(team_games, start=1):
            game.gameNumber = i
