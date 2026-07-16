"""
OddsPortal scraper for NBA moneyline data.

Scrapes game results and moneyline odds from OddsPortal.com for NBA regular seasons.
OddsPortal provides average moneyline odds across many bookmakers.

Created in November 2024. If OddsPortal changes their website structure, 
this scraper may need updates.
"""

from typing import List, Dict
from core.game import Game
from core.base_scraper import BaseScraper
from core.selenium_webdriver import SeleniumWebDriver
from oddsportal.helpers import makeUrl, getLastPageNum, getDateHeaderRow, isRegularSeason, scrapeGamesFromRow, reverseGameNumbers


class OddsPortalScraper(BaseScraper, SeleniumWebDriver):
    """
    Scraper for OddsPortal NBA moneyline data.
    
    Scrapes historical NBA game results with moneyline odds from oddsportal.com.
    Inherits WebDriver automation from SeleniumWebDriver for dynamic page handling.
    """
    
    # Initialize the OddsPortal scraper.
    def __init__(self, headless: bool = False):
        SeleniumWebDriver.__init__(self, headless)
        # Carries over across page boundaries: a date's games can legitimately
        # span two pages, and the date header only appears once (on whichever
        # page that date started on), so this must not reset per-page.
        self._isRegularSeasonNow = False
        # Tracks the largest non-header eventRow count seen on a "good" page
        # so far this season, used to detect pages that rendered a stale/
        # partial loading skeleton instead of the full row set.
        self._max_nonheader_rows_seen = 0
    
    # Returns list of URLs for all pages of a season's results.
    def getSeasonScheduleLinks(self, seasonStartYear: int) -> List[str]:
        url = makeUrl(seasonStartYear, 1)
        self.loadWebPage(url)
        self.waitForElement('.pagination-link[data-number]')
        soup = self.makeSoup()
        lastPageNum = getLastPageNum(soup)
        return [makeUrl(seasonStartYear, pageNum) for pageNum in range(1, lastPageNum + 1)]
    
    # Scrapes all games from a single OddsPortal results page.
    def scrapeGamesFromPage(self, url: str, page_num: int, seasonStartYear: int, games: Dict[str, List[Game]],
                             max_attempts: int = 5):
        gameRows = None
        for attempt in range(1, max_attempts + 1):
            try:
                # Launch oddsportal webpage
                self.loadWebPage(url)

                # Wait for the active pagination link to confirm page load
                self.waitForElement(f"a.pagination-link.active[data-number='{page_num}']")

                # Wait for "Add to My Leagues" button to confirm game table is loaded
                self.waitForElement('[data-testid="add-to-my-leagues-button"]')

                # Wait for the event row count to stop changing before parsing, so we
                # don't scrape mid-transition (causes missed or duplicated boundary games).
                # A loading skeleton can render a handful of eventRow-classed
                # placeholders that sit unchanged for a few seconds while the
                # real data streams in behind it, so require a long, patient
                # stable window rather than a quick one.
                self.waitForStableElementCount(".eventRow", stable_checks=6, poll_interval=1.5, timeout=30)

                soup = self.makeSoup()
                gameRows = soup.find_all(class_="eventRow")

                header_count = sum(1 for r in gameRows if getDateHeaderRow(r) is not None)
                non_header_rows = len(gameRows) - header_count
                rows_with_game_data = sum(1 for r in gameRows if r.select_one('[data-testid="game-row"]') is not None)

                # Sanity check 1: on a fully-rendered page, almost every non-header
                # eventRow should be a parseable game row (the only legitimate
                # exclusions are rare odds-missing fallback failures). If most
                # non-header rows have no `game-row` testid at all, the DOM
                # likely stalled mid-render (stale/partial content).
                if non_header_rows > 0 and rows_with_game_data / non_header_rows < 0.8:
                    raise RuntimeError(
                        f"Page {page_num} looks incompletely rendered: only "
                        f"{rows_with_game_data}/{non_header_rows} non-header rows had game data"
                    )

                # Sanity check 2: compare against the largest row count seen on
                # a good page so far this season. A page with far fewer rows
                # than the established norm is likely a stale loading skeleton
                # that happened to be internally consistent (so check 1 alone
                # wouldn't catch it), not a genuinely quiet day.
                if self._max_nonheader_rows_seen >= 20 and non_header_rows < 0.5 * self._max_nonheader_rows_seen:
                    raise RuntimeError(
                        f"Page {page_num} has only {non_header_rows} non-header rows, "
                        f"vs. {self._max_nonheader_rows_seen} seen on a prior page this season"
                    )

                self._max_nonheader_rows_seen = max(self._max_nonheader_rows_seen, non_header_rows)
                break
            except Exception as e:
                print(f"  ⚠️  Attempt {attempt}/{max_attempts} failed to load page {page_num} ({e.__class__.__name__}: {e}), retrying...")
        else:
            print(f"  ❌ Page {page_num} still looked incomplete after {max_attempts} attempts — "
                  f"proceeding with the last attempt's content. Verify this page's counts manually.")

        for gameRow in gameRows:
            dateHeaderRow= getDateHeaderRow(gameRow)
            if dateHeaderRow is not None:
                self._isRegularSeasonNow = isRegularSeason(dateHeaderRow)
            if self._isRegularSeasonNow:
                scrapeGamesFromRow(gameRow, seasonStartYear, games, self.driver)
    
    # Scrapes all games for a season (with OddsPortal-specific handling).        
    def scrapeSeasonSchedule(self, seasonStartYear: int) -> Dict[str, List[Game]]:
        games = {}
        urls = self.getSeasonScheduleLinks(seasonStartYear)
        
        total_games_scraped = 0
        
        # Initialize driver once for the entire season
        self.initDriver()
        try:
            for i, url in enumerate(urls, start=1):
                print(f"Scraping page {i}/{len(urls)}...")
                games_before = sum(len(team_games) for team_games in games.values())
                self.scrapeGamesFromPage(url, i, seasonStartYear, games)
                games_after = sum(len(team_games) for team_games in games.values())
                games_on_page = games_after - games_before
                total_games_scraped += games_on_page
                print(f"  → {games_on_page} games scraped from page {i}")
        finally:
            self.quitDriver()
        
        print(f"\n{'='*60}")
        print(f"Total games scraped: {total_games_scraped}")
        print(f"Total game objects (2 per game): {sum(len(team_games) for team_games in games.values())}")
        print(f"Expected: 2460 games = 4920 game objects")
        print(f"{'='*60}\n")
        
        # Fix game numbers (OddsPortal lists games in reverse chronological order)
        reverseGameNumbers(games)
        
        return games
