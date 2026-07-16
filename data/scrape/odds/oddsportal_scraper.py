"""
OddsPortal scraper for NBA moneyline data.

Scrapes game results and moneyline odds from OddsPortal.com for NBA regular seasons.
OddsPortal provides average moneyline odds across many bookmakers.

Created in November 2024. If OddsPortal changes their website structure,
this scraper may need updates.

Combines Selenium browser automation and OddsPortal-specific scraping logic
in one class. These used to be split across a base class (generic Selenium
mechanics) and a subclass (OddsPortal specifics), on the theory that the
base class could be reused for a future second dynamic-site scraper - but
no second one ever showed up, and OddsPortal-specific knowledge (the Vue
router reload workaround, the OneTrust cookie-consent selector) had already
leaked into the "generic" class anyway. One class is more honest about what
this actually is.

A three-way fetcher/parser/orchestrator file split (mirroring schedules/)
was considered and rejected: unlike schedules/fetcher.py, judging whether
an OddsPortal page fetch actually succeeded requires inspecting parsed
content (the sanity checks below), so "fetching" and "enough parsing to
judge quality" aren't independent concerns here the way they are for a
plain HTTP GET. Splitting across files would mean threading self.driver
and self._max_nonheader_rows_seen across module boundaries for a benefit
that's mostly aesthetic. Instead, this class is organized into four
sections matching its real seams: session/automation primitives,
resilient page-fetch, row-level data extraction, and season orchestration.

A standalone parser.py used to hold the pure helpers below too, but that
implied "this is where OddsPortal parsing lives" when most of the real
parsing (row/odds/winner extraction) is on the class itself, and nothing
outside this file and its tests ever imported it. Kept here instead as a
labeled preamble - same pure/stateless/no-driver property, same easy
testability, just without the misleading separate-file framing.
"""

import os
import time
from typing import List, Dict, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from util.game import Game


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#   PURE HELPERS (URL construction + HTML         #
#   parsing, no live driver needed)               #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

# OddsPortal only gives a season its own archived results URL once a newer
# season has started; the most recently completed season is only reachable
# via the generic (season-agnostic) "current results" URL until then. Both
# URLs are needed - see _resolveSeasonUrlBuilder below, which live-checks
# which one applies for the requested season rather than hardcoding an
# assumption that breaks as soon as a new season starts.

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


class OddsPortalScraper:
    """
    Scraper for OddsPortal NBA moneyline data.

    Scrapes historical NBA game results with moneyline odds from oddsportal.com,
    including the Selenium browser automation needed to handle its dynamic,
    JS-rendered pages.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.wait_time = 10
        self.driver = None
        # Carries over across page boundaries: a date's games can legitimately
        # span two pages, and the date header only appears once (on whichever
        # page that date started on), so this must not reset per-page.
        self._isRegularSeasonNow = False
        # Tracks the largest non-header eventRow count seen on a "good" page
        # so far this season, used to detect pages that rendered a stale/
        # partial loading skeleton instead of the full row set.
        self._max_nonheader_rows_seen = 0

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 1: SESSION + AUTOMATION PRIMITIVES    #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def initDriver(self):
        """Initialize Selenium WebDriver with optimized settings."""
        if self.driver is not None:
            return self.driver

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")

        # Disable images, stylesheets, and fonts for faster loading
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
        }
        options.add_experimental_option("prefs", prefs)

        self.driver = webdriver.Chrome(options=options)

        # --- IMPORTANT: Disable browser cache so single-page-apps (SPAs) fully reload ---
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})

        return self.driver

    def quitDriver(self):
        """Close the WebDriver if it's open."""
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

    def loadWebPage(self, url: str):
        """
        Load a web page using the WebDriver.

        Args:
            url (str): URL of the page to load
        """
        if self.driver is None:
            self.initDriver()

        self.driver.get(url)

        # --- IMPORTANT: Force a TRUE network reload to defeat OddsPortal's Vue router caching ---
        self.driver.execute_script("location.reload(true);")

        time.sleep(4)

        # A cookie-consent modal (OneTrust) can cover the whole page and block
        # the underlying results content from ever rendering, which would
        # otherwise silently time out every wait downstream with no clear
        # cause. It only needs dismissing once per browser session, but
        # forcing a true reload on every page load risks it resurfacing, so
        # check (cheaply) on every load rather than assuming once is enough.
        self.dismissCookieConsentIfPresent()

        # Scroll to load all lazy-loaded content
        self.scrollToBottom()

    def dismissCookieConsentIfPresent(self):
        """
        Click through OddsPortal's OneTrust cookie-consent banner if it's
        covering the page. An instant (non-waiting) check: by the time this
        is called we've already slept after navigation, so the banner - if
        it's going to appear at all - is already in the DOM. Not waiting
        here avoids adding dead latency to every page load in the common
        case where the banner was already dismissed earlier in this browser
        session.
        """
        try:
            buttons = self.driver.find_elements(By.ID, "onetrust-reject-all-handler")
            if buttons:
                buttons[0].click()
                time.sleep(1)  # let the modal finish closing before we scroll/parse
        except Exception:
            pass  # not present this load - already dismissed, or this page doesn't show it

    def scrollToBottom(self):
        """
        Scroll to bottom of page to trigger lazy loading.

        Scrolls in increments to ensure lazy-loaded content is triggered.
        """
        if self.driver is None:
            raise RuntimeError("Driver not initialized. Call initDriver() first.")

        # Get initial page height
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        # Scroll in smaller increments to trigger lazy loading
        current_position = 0
        scroll_increment = 200  # pixels to scroll at a time

        while current_position < last_height:
            # Scroll down by increment
            current_position += scroll_increment
            self.driver.execute_script(f"window.scrollTo(0, {current_position});")
            time.sleep(1.5)  # Wait for content to load

            # Check if page height increased (new content loaded)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height > last_height:
                last_height = new_height

        # Final scroll to absolute bottom
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

    def waitForElement(self, css_selector: str):
        """
        Wait for an element to be present on the page.

        Args:
            css_selector (str): CSS selector of the element to wait for
        """
        if self.driver is None:
            raise RuntimeError("Driver not initialized. Call initDriver() first.")

        WebDriverWait(self.driver, self.wait_time).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css_selector))
        )
        time.sleep(2)  # Additional wait to ensure content is fully loaded

    def waitForStableElementCount(self, css_selector: str, min_count: int = 1,
                                   stable_checks: int = 3, poll_interval: float = 1.0,
                                   timeout: float = 20.0):
        """
        Wait until the number of elements matching css_selector stops changing.

        Guards against scraping a page mid-transition: on a slow render, the
        pagination-active-link/button can appear before the game rows have
        finished swapping in (or while stale rows from the previous page are
        still being removed), which causes games to be missed or duplicated
        across the page boundary. Polling the row count until it's stable
        confirms the DOM has actually settled before we parse it.

        Args:
            css_selector: CSS selector of the repeating elements to count (e.g. eventRow)
            min_count: minimum element count required before considering it stable
            stable_checks: number of consecutive matching counts required
            poll_interval: seconds between polls
            timeout: max seconds to wait before giving up and proceeding anyway
        """
        if self.driver is None:
            raise RuntimeError("Driver not initialized. Call initDriver() first.")

        start = time.time()
        last_count = -1
        consecutive_matches = 0

        while time.time() - start < timeout:
            count = len(self.driver.find_elements(By.CSS_SELECTOR, css_selector))
            if count >= min_count and count == last_count:
                consecutive_matches += 1
                if consecutive_matches >= stable_checks:
                    return count
            else:
                consecutive_matches = 0
            last_count = count
            time.sleep(poll_interval)

        print(f"  ⚠️  Element count for '{css_selector}' never stabilized within {timeout}s (last count: {last_count})")
        return last_count

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 2: RESILIENT PAGE-FETCH               #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    # Makes one live attempt to fetch and validate a results page: navigate,
    # wait for the DOM to settle, then run both sanity checks. Raises if
    # either check fails - the caller's retry loop decides what to do with
    # that. Kept separate from scrapeGamesFromPage's cache/retry/circuit-
    # breaker orchestration so each has one job: this makes one attempt and
    # judges it; the caller decides how many attempts to allow.
    def _attemptPageFetch(self, url: str, page_num: int):
        """
        Returns:
            tuple: (html: str, gameRows: list of eventRow elements) for a
            page that passed both sanity checks.
        """
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

        html = self.driver.page_source
        soup = BeautifulSoup(html, "lxml")
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

        return html, gameRows

    # Fetches all games from a single OddsPortal results page, checking the
    # local cache first, then retrying live attempts up to max_attempts.
    # Returns True if the page rendered successfully within max_attempts (or
    # was already cached from a prior successful run), False if we had to
    # give up and proceed with the last (possibly incomplete) attempt's
    # content - the caller uses this to detect a site-wide outage/block
    # rather than silently completing with bad data.
    def scrapeGamesFromPage(self, url: str, page_num: int, seasonStartYear: int, games: Dict[str, List[Game]],
                             max_attempts: int = 5, cache_dir: Optional[str] = None) -> bool:
        # Cache is keyed by page number, mirroring schedules/fetcher.py's
        # per-team cache: lets a re-run (e.g. after OddsPortal rate-limits
        # mid-scrape) skip straight past every page that already rendered
        # successfully, instead of re-scraping the whole season from page 1.
        cache_path = os.path.join(cache_dir, f"page_{page_num}.html") if cache_dir else None

        if cache_path and os.path.exists(cache_path):
            print(f"  💾 Using cached HTML for page {page_num}")
            with open(cache_path, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "lxml")
            gameRows = soup.find_all(class_="eventRow")
            succeeded = True
        else:
            # Starts empty rather than None: if every attempt fails before ever
            # reaching soup.find_all() below (e.g. the pagination-link wait times
            # out on every retry), there's no "last attempt's content" to fall
            # back to. Treating that as zero rows lets the caller's consecutive-
            # failure circuit breaker do its job instead of crashing here on a
            # NoneType iteration error that would mask the real signal.
            gameRows = []
            succeeded = False
            html = None
            for attempt in range(1, max_attempts + 1):
                try:
                    html, gameRows = self._attemptPageFetch(url, page_num)
                    succeeded = True
                    break
                except Exception as e:
                    print(f"  ⚠️  Attempt {attempt}/{max_attempts} failed to load page {page_num} ({e.__class__.__name__}: {e}), retrying...")
            else:
                print(f"  ❌ Page {page_num} still looked incomplete after {max_attempts} attempts — "
                      f"proceeding with the last attempt's content. Verify this page's counts manually.")

            # Only cache pages that actually passed the sanity checks above -
            # a flaky/incomplete render must never be "locked in" as if it
            # were good, or a re-run would silently keep reusing bad data
            # instead of retrying it live.
            if succeeded and cache_path:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(html)

        for gameRow in gameRows:
            dateHeaderRow= getDateHeaderRow(gameRow)
            if dateHeaderRow is not None:
                self._isRegularSeasonNow = isRegularSeason(dateHeaderRow)
            if self._isRegularSeasonNow:
                self.scrapeGamesFromRow(gameRow, seasonStartYear, games)

        return succeeded

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 3: ROW-LEVEL DATA EXTRACTION           #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    # Scrape a single game (both home & away) from a table row and add to games dictionary.
    def scrapeGamesFromRow(self, row, seasonStartYear: int, games: Dict[str, List[Game]]):
        gameRow = row.select_one('[data-testid="game-row"]')

        if not gameRow:
            print("  ⚠️  No game-row found in row, skipping")
            return

        teams = gameRow.select('p.participant-name')
        if len(teams) < 2:
            print(f"  ⚠️  Not enough team names found (found {len(teams)}), skipping game")
            return

        homeTeamName = teams[0].text.strip()
        awayTeamName = teams[1].text.strip()

        odds_and_winner = self._extractOddsAndWinner(gameRow, row, homeTeamName, awayTeamName)
        if odds_and_winner is None:
            return
        homeWon, awayWon, homeWinOdds, awayWinOdds = odds_and_winner

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

    # Determines the winner and moneyline odds for a game row: uses the
    # odds already present in the row if OddsPortal rendered them there,
    # falling back to a live fetch of the game's own detail page if not.
    def _extractOddsAndWinner(self, gameRow, row, homeTeamName: str, awayTeamName: str):
        """
        Returns:
            Optional[tuple]: (homeWon, awayWon, homeWinOdds, awayWinOdds),
            or None if odds couldn't be determined at all (caller should
            skip this game).
        """
        odds_elements = gameRow.select('p[data-testid^="odd-container"]')

        if odds_elements is None or len(odds_elements) < 2:
            # Fallback for missing odds
            print(f"  ⚠️  Missing odds for {homeTeamName} vs {awayTeamName}, using fallback...")

            # Save the HTML for debugging
            debug_dir = "/tmp/moneyline_debug"
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, f"{homeTeamName}_vs_{awayTeamName}.html")
            with open(debug_file, 'w') as f:
                f.write(str(row.prettify()))
            print(f"  → Saved HTML to {debug_file}")

            homeWon, awayWon, homeWinOdds, awayWinOdds = self._fetchOddsFromDetailPage(row)

            if homeWinOdds == -1 or awayWinOdds == -1:
                print(f"  ❌ SKIPPED: {homeTeamName} vs {awayTeamName} (fallback failed)")
                return None

            return homeWon, awayWon, homeWinOdds, awayWinOdds

        homeWon = "winning" in odds_elements[0].get("data-testid", "")
        awayWon = "winning" in odds_elements[1].get("data-testid", "")
        try:
            homeWinOdds = int(odds_elements[0].text.strip())
            awayWinOdds = int(odds_elements[1].text.strip())
        except (ValueError, AttributeError) as e:
            print(f"  ❌ SKIPPED: {homeTeamName} vs {awayTeamName} (error parsing odds: {e})")
            return None

        return homeWon, awayWon, homeWinOdds, awayWinOdds

    def _fetchOddsFromDetailPage(self, row):
        """
        Fallback for when odds aren't shown on the main results page:
        navigates to the individual game's detail page to get them, and
        determines the winner from the original row HTML.

        Args:
            row: BeautifulSoup element of the game row

        Returns:
            tuple: (homeWon, awayWon, homeWinOdds, awayWinOdds)
        """
        # Find the game detail page link
        game_row_div = row.select_one('[data-testid="game-row"]')
        first_link = game_row_div.find('a', href=True)

        if not first_link:
            print("  ⚠️  No link found in game row, returning defaults")
            return False, False, -1, -1

        # Navigate to the game detail page
        game_url = "https://www.oddsportal.com" + first_link['href']
        print(f"  → Fetching odds from detail page: {game_url}")
        self.driver.get(game_url)

        # Wait for odds to load
        try:
            self.waitForElement('[data-testid="odd-container"]')
        except Exception:
            print("  ⚠️  Timeout waiting for odds on detail page")
            return False, False, -1, -1

        # Get the odds from the detail page
        detail_soup = BeautifulSoup(self.driver.page_source, "lxml")
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

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 4: SEASON-LEVEL ORCHESTRATION          #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

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
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        lastPageNum = getLastPageNum(soup)
        return [buildUrl(pageNum) for pageNum in range(1, lastPageNum + 1)]

    # Scrapes all games for a season (with OddsPortal-specific handling).
    # cache_dir: if given, each page's rendered HTML is cached there once it
    # passes scrapeGamesFromPage's sanity checks, so a re-run after a
    # mid-scrape failure (e.g. OddsPortal rate-limiting) can resume from
    # where it left off instead of re-scraping every page from scratch.
    def scrapeSeasonSchedule(self, seasonStartYear: int, cache_dir: Optional[str] = None) -> Dict[str, List[Game]]:
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
                page_succeeded = self.scrapeGamesFromPage(url, i, seasonStartYear, games, cache_dir=cache_dir)
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
