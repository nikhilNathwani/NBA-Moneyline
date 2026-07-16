"""
Pure URL-construction and HTML-parsing functions for the OddsPortal
scraper: everything parameterized purely by its arguments, no live driver
access, which is what makes it independently unit-testable (see
test_urls.py, test_parsing.py) without any Selenium setup.

Includes the row-level and detail-page-level odds/winner extraction too -
"parsing" here means interpreting HTML already in hand, whether that HTML
came from the main results page or a live re-fetch of a game's detail
page. What stays out of this file is the live re-fetching itself (that
needs self.driver, so it lives on OddsPortalScraper), not the parsing of
what comes back from it.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Optional

from util.game import Game

# OddsPortal only gives a season its own archived results URL once a newer
# season has started; the most recently completed season is only reachable
# via the generic (season-agnostic) "current results" URL until then. Both
# URLs are needed - see _resolveSeasonUrlBuilder in oddsportal_scraper.py,
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

# Count how many of a page's eventRow elements are non-header rows, and how
# many of those actually contain parseable game data - used by
# OddsPortalScraper's fetch-quality sanity checks to judge whether a page
# rendered completely.
def countGameDataRows(gameRows) -> tuple:
    """Returns: tuple: (non_header_rows: int, rows_with_game_data: int)"""
    header_count = sum(1 for r in gameRows if getDateHeaderRow(r) is not None)
    non_header_rows = len(gameRows) - header_count
    rows_with_game_data = sum(1 for r in gameRows if r.select_one('[data-testid="game-row"]') is not None)
    return non_header_rows, rows_with_game_data


class RowOddsResult(Enum):
    SUCCESS = auto()
    NEEDS_FALLBACK = auto()  # odds missing from the row entirely - caller should try the detail-page fallback
    PARSE_ERROR = auto()     # odds present but unparseable - caller should just skip, fallback won't help


@dataclass
class RowOddsExtraction:
    result: RowOddsResult
    odds: Optional[tuple] = None  # (homeWon, awayWon, homeWinOdds, awayWinOdds), only set when result is SUCCESS
    error: Optional[str] = None   # only set when result is PARSE_ERROR


# Attempt to extract winner and moneyline odds directly from a game row's
# HTML (the fast path - most rows have this).
def extractOddsAndWinnerFromRow(gameRow) -> RowOddsExtraction:
    odds_elements = gameRow.select('p[data-testid^="odd-container"]')

    if odds_elements is None or len(odds_elements) < 2:
        return RowOddsExtraction(result=RowOddsResult.NEEDS_FALLBACK)

    homeWon = "winning" in odds_elements[0].get("data-testid", "")
    awayWon = "winning" in odds_elements[1].get("data-testid", "")
    try:
        homeWinOdds = int(odds_elements[0].text.strip())
        awayWinOdds = int(odds_elements[1].text.strip())
    except (ValueError, AttributeError) as e:
        return RowOddsExtraction(result=RowOddsResult.PARSE_ERROR, error=str(e))

    return RowOddsExtraction(result=RowOddsResult.SUCCESS, odds=(homeWon, awayWon, homeWinOdds, awayWinOdds))


# Find the href to a game's individual detail page, if present in the row.
def findDetailPageLink(row) -> Optional[str]:
    game_row_div = row.select_one('[data-testid="game-row"]')
    first_link = game_row_div.find('a', href=True)
    return first_link['href'] if first_link else None


# Parse odds and determine the winner from a game's detail page, given its
# already-fetched HTML and the original row (winner detection reads the
# row, not the detail page - the detail page doesn't mark it the same way).
def extractOddsFromDetailSoup(detail_soup, row) -> tuple:
    """
    Returns:
        tuple: (homeWon, awayWon, homeWinOdds, awayWinOdds). homeWinOdds/
        awayWinOdds are -1 if odds couldn't be found/parsed at all.
    """
    odds_elements = detail_soup.select('[data-testid="odd-container"]')

    if len(odds_elements) < 2:
        print("  ⚠️  Not enough odds elements found on detail page")
        return False, False, -1, -1

    try:
        homeWinOdds = int(odds_elements[0].text.strip())
        awayWinOdds = int(odds_elements[1].text.strip())
    except (ValueError, AttributeError) as e:
        print(f"  ⚠️  Error parsing odds: {e}")
        return False, False, -1, -1

    # Determine winner from original row
    participant_names = row.select('p.participant-name')

    if len(participant_names) < 2:
        print("  ⚠️  Not enough participant names found")
        return False, False, homeWinOdds, awayWinOdds

    # Check if the first participant's parent div has 'font-bold' class
    # indicating they won
    first_participant_parent = participant_names[0].parent

    if first_participant_parent and 'font-bold' in first_participant_parent.get('class', []):
        homeWon = True
        awayWon = False
    else:
        homeWon = False
        awayWon = True

    print(f"  ✓ Odds retrieved: Home={homeWinOdds}, Away={awayWinOdds}, HomeWon={homeWon}")

    return homeWon, awayWon, homeWinOdds, awayWinOdds


# Fix game numbers to be in chronological order.
# (OddsPortal lists games in reverse chronological order, so I reverse & renumber them)
def reverseGameNumbers(games: Dict[str, List[Game]]):
    for team, team_games in games.items():
        # Reverse the list so it's in chronological order
        team_games.reverse()
        # Assign game numbers
        for i, game in enumerate(team_games, start=1):
            game.gameNumber = i
