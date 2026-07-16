"""
OddsPortal scraper for NBA moneyline data.

Scrapes game results and moneyline odds from OddsPortal.com for NBA regular seasons.
OddsPortal provides average moneyline odds across many bookmakers.

Created in November 2024. If OddsPortal changes their website structure, 
this scraper may need updates.
"""

from typing import List, Dict
from util.scraping.game import Game
from util.scraping.selenium_webdriver import SeleniumWebDriver
from odds.helpers import (
    makeSeasonSpecificUrl, makeCurrentSeasonUrl, urlMatchesRequestedSeason,
    getLastPageNum, getDateHeaderRow, isRegularSeason, scrapeGamesFromRow, reverseGameNumbers
)


class OddsPortalScraper(SeleniumWebDriver):
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
    
    # Determines whether the requested season is already archived under its own
    # OddsPortal URL, or is still only reachable via the generic "current
    # results" page (true for whichever season was most recently completed,
    # until a newer one starts), and returns a pageNum -> URL builder for
    # whichever applies. Leaves the driver on page 1 of that URL scheme, so
    # getSeasonScheduleLinks doesn't need to load it a second time.
    def _resolveSeasonUrlBuilder(self, seasonStartYear: int):
        season_specific_url = makeSeasonSpecificUrl(seasonStartYear, 1)
        self.loadWebPage(season_specific_url)
        if urlMatchesRequestedSeason(self.driver.current_url, seasonStartYear):
            return lambda pageNum: makeSeasonSpecificUrl(seasonStartYear, pageNum)

        print(f"  ℹ️  {seasonStartYear}-{(seasonStartYear+1)%100:02d} isn't archived under its own "
              f"OddsPortal URL yet (that only happens once a newer season has started) — "
              f"falling back to the generic current-results page.")
        self.loadWebPage(makeCurrentSeasonUrl(1))
        return lambda pageNum: makeCurrentSeasonUrl(pageNum)

    # Returns list of URLs for all pages of a season's results.
    def getSeasonScheduleLinks(self, seasonStartYear: int) -> List[str]:
        buildUrl = self._resolveSeasonUrlBuilder(seasonStartYear)
        self.waitForElement('.pagination-link[data-number]')
        soup = self.makeSoup()
        lastPageNum = getLastPageNum(soup)
        return [buildUrl(pageNum) for pageNum in range(1, lastPageNum + 1)]
    
    # Scrapes all games from a single OddsPortal results page.
    # Returns True if the page rendered successfully within max_attempts,
    # False if we had to give up and proceed with the last (possibly
    # incomplete) attempt's content - the caller uses this to detect a
    # site-wide outage/block rather than silently completing with bad data.
    def scrapeGamesFromPage(self, url: str, page_num: int, seasonStartYear: int, games: Dict[str, List[Game]],
                             max_attempts: int = 5) -> bool:
        # Starts empty rather than None: if every attempt fails before ever
        # reaching soup.find_all() below (e.g. the pagination-link wait times
        # out on every retry), there's no "last attempt's content" to fall
        # back to. Treating that as zero rows lets the caller's consecutive-
        # failure circuit breaker do its job instead of crashing here on a
        # NoneType iteration error that would mask the real signal.
        gameRows = []
        succeeded = False
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
                succeeded = True
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

        return succeeded
    
    # Scrapes all games for a season (with OddsPortal-specific handling).
    def scrapeSeasonSchedule(self, seasonStartYear: int) -> Dict[str, List[Game]]:
        games = {}
        urls = self.getSeasonScheduleLinks(seasonStartYear)

        total_games_scraped = 0
        consecutive_page_failures = 0
        MAX_CONSECUTIVE_PAGE_FAILURES = 3

        # Initialize driver once for the entire season
        self.initDriver()
        try:
            for i, url in enumerate(urls, start=1):
                print(f"Scraping page {i}/{len(urls)}...")
                games_before = sum(len(team_games) for team_games in games.values())
                page_succeeded = self.scrapeGamesFromPage(url, i, seasonStartYear, games)
                games_after = sum(len(team_games) for team_games in games.values())
                games_on_page = games_after - games_before
                total_games_scraped += games_on_page
                print(f"  → {games_on_page} games scraped from page {i}")

                # A handful of isolated page failures can be a transient render
                # race (already retried and logged above). But several pages
                # in a row failing to render at all - even after every retry -
                # points to something systemic (e.g. OddsPortal rate-limiting
                # or blocking this session), where keep going would silently
                # produce a badly incomplete "complete-looking" dataset
                # instead of a clear, actionable failure.
                if page_succeeded:
                    consecutive_page_failures = 0
                else:
                    consecutive_page_failures += 1
                    if consecutive_page_failures >= MAX_CONSECUTIVE_PAGE_FAILURES:
                        raise RuntimeError(
                            f"{consecutive_page_failures} consecutive pages failed to render "
                            f"even after retries (most recently page {i}/{len(urls)}). This "
                            f"usually means OddsPortal is rate-limiting or blocking automated "
                            f"requests, not a one-off render race - aborting rather than "
                            f"silently producing an incomplete dataset. Wait a while before "
                            f"retrying, or check manually whether the site structure changed."
                        )
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
