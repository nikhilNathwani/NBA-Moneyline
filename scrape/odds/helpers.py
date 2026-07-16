from typing import List, Dict
from utils.game import Game


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#                                               #
#              HELPER FUNCTIONS                 #
#                                               #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

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

# Scrape a single game (both home & away) from a table row and add to games dictionary.
def scrapeGamesFromRow(row, seasonStartYear: int, games: Dict[str, List[Game]], driver=None):
    gameRow = row.select_one('[data-testid="game-row"]')
    
    if not gameRow:
        print("  ⚠️  No game-row found in row, skipping")
        return
    
    # Extract odds elements and team names
    odds_elements = gameRow.select('p[data-testid^="odd-container"]')
    teams = gameRow.select('p.participant-name')
    
    if len(teams) < 2:
        print(f"  ⚠️  Not enough team names found (found {len(teams)}), skipping game")
        return
    
    homeTeamName = teams[0].text.strip()
    awayTeamName = teams[1].text.strip()
    
    # Parse outcomes and odds
    if odds_elements is None or len(odds_elements) < 2:
        # Fallback for missing odds
        print(f"  ⚠️  Missing odds for {homeTeamName} vs {awayTeamName}, using fallback...")
        
        # Save the HTML for debugging
        import os
        debug_dir = "/tmp/moneyline_debug"
        os.makedirs(debug_dir, exist_ok=True)
        debug_file = os.path.join(debug_dir, f"{homeTeamName}_vs_{awayTeamName}.html")
        with open(debug_file, 'w') as f:
            f.write(str(row.prettify()))
        print(f"  → Saved HTML to {debug_file}")
        
        if driver is None:
            print("  ⚠️  No driver provided for fallback, skipping game")
            return
        homeWon, awayWon, homeWinOdds, awayWinOdds = fallback_noOddsInRow(row, driver)
        
        # Check if fallback failed
        if homeWinOdds == -1 or awayWinOdds == -1:
            print(f"  ❌ SKIPPED: {homeTeamName} vs {awayTeamName} (fallback failed)")
            return
    else:
        homeWon = "winning" in odds_elements[0].get("data-testid", "")
        awayWon = "winning" in odds_elements[1].get("data-testid", "")
        try:
            homeWinOdds = int(odds_elements[0].text.strip())
            awayWinOdds = int(odds_elements[1].text.strip())
        except (ValueError, AttributeError) as e:
            print(f"  ❌ SKIPPED: {homeTeamName} vs {awayTeamName} (error parsing odds: {e})")
            return
    
    # Guard against re-scraping the same game twice.
    # This happens when a page transition races ahead of the DOM swap (the
    # last game row of the previous page is still present when the next
    # page is scraped) or when a page renders a "featured game" widget that
    # duplicates a row already present elsewhere in the same page's list.
    # Both failure modes only ever duplicate a row that was scraped very
    # recently (same page or an adjacent one), so only look back a bounded
    # window rather than the team's whole-season history: two genuinely
    # different games between the same two teams, weeks apart, can
    # occasionally share identical odds by coincidence, and checking the
    # full history would wrongly drop that second, legitimate game.
    RECENT_DUPLICATE_LOOKBACK = 8
    existing_home_games = games.get(homeTeamName, [])
    if any(g.opponent == awayTeamName and g.outcome == homeWon
           and g.winOdds == homeWinOdds and g.loseOdds == awayWinOdds
           for g in existing_home_games[-RECENT_DUPLICATE_LOOKBACK:]):
        print(f"  ⚠️  Skipping duplicate game row: {homeTeamName} vs {awayTeamName} (already scraped)")
        return

    # Create game objects (gameNumber will be set later during post-processing)
    homeGame = Game(
        team=homeTeamName,
        opponent=awayTeamName,
        outcome=homeWon,
        winOdds=homeWinOdds,
        loseOdds=awayWinOdds,
        seasonStartYear=seasonStartYear
    )

    awayGame = Game(
        team=awayTeamName,
        opponent=homeTeamName,
        outcome=awayWon,
        winOdds=awayWinOdds,
        loseOdds=homeWinOdds,
        seasonStartYear=seasonStartYear
    )

    # Add games to dictionary (game numbers will be set later)
    for game in [homeGame, awayGame]:
        if game.team not in games:
            games[game.team] = []
        games[game.team].append(game)

# Fix game numbers to be in chronological order.
# (OddsPortal lists games in reverse chronological order, so I reverse & renumber them)    
def reverseGameNumbers(games: Dict[str, List[Game]]):
    for team, team_games in games.items():
        # Reverse the list so it's in chronological order
        team_games.reverse()
        # Assign game numbers
        for i, game in enumerate(team_games, start=1):
            game.gameNumber = i

def fallback_noOddsInRow(row, driver):
    """
    Fallback function to scrape odds when they're not shown on the main page.
    
    Navigates to the individual game page to get the odds, and determines the winner
    from the original row HTML.
    
    Args:
        row: BeautifulSoup element of the game row
        driver: Selenium WebDriver instance to navigate to game detail page
        
    Returns:
        tuple: (homeWon, awayWon, homeWinOdds, awayWinOdds)
    """
    from bs4 import BeautifulSoup
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import time
    
    # Find the game detail page link
    game_row_div = row.select_one('[data-testid="game-row"]')
    first_link = game_row_div.find('a', href=True)
    
    if not first_link:
        print("  ⚠️  No link found in game row, returning defaults")
        return False, False, -1, -1
    
    # Navigate to the game detail page
    game_url = "https://www.oddsportal.com" + first_link['href']
    print(f"  → Fetching odds from detail page: {game_url}")
    driver.get(game_url)
    
    # Wait for odds to load
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="odd-container"]'))
        )
        time.sleep(2)  # Additional wait for full rendering
    except:
        print("  ⚠️  Timeout waiting for odds on detail page")
        return False, False, -1, -1
    
    # Get the odds from the detail page
    detail_soup = BeautifulSoup(driver.page_source, "lxml")
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
    # Find the participant-name elements
    participant_names = row.select('p.participant-name')
    
    if len(participant_names) < 2:
        print("  ⚠️  Not enough participant names found")
        return False, False, homeWinOdds, awayWinOdds
    
    # Check if the first participant's parent div has 'font-bold' class
    # indicating they won
    first_participant_parent = participant_names[0].parent
    
    # Navigate up to find the div with font-bold class
    homeWon = False
    awayWon = False
    
    # The parent div structure might vary, so check the immediate parent
    # and its classes
    if first_participant_parent and 'font-bold' in first_participant_parent.get('class', []):
        homeWon = True
        awayWon = False
    else:
        homeWon = False
        awayWon = True
    
    print(f"  ✓ Odds retrieved: Home={homeWinOdds}, Away={awayWinOdds}, HomeWon={homeWon}")
    
    return homeWon, awayWon, homeWinOdds, awayWinOdds