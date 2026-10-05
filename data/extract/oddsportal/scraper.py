"""
OddsPortal scraper for NBA moneyline data.

Scrapes game results and moneyline odds from OddsPortal.com for NBA regular
seasons. OddsPortal shows each game's average odds across the bookmakers it
has on record for it (how many varies by season - e.g. 1 for 2023-24, 4 for
2025-26 as of October 2026 - and the averages can drift a little over time as
that set changes).

Rewritten in October 2026 for OddsPortal's redesigned site. If the site
changes again, this file and parser.py are what need updating.

Owns everything that needs a live Selenium session: the browser, the odds-
format setting, moving between result pages, the resilient page fetch
(retry / sanity-check / cache), and season-level orchestration. Delegates
everything parseable-in-hand (URLs, HTML interpretation, turning rows into
per-team games) to parser.py.
"""

import os
import time
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from util.constants import FIRST_IST_SEASON
from util.records import TeamGame
from extract.oddsportal.parser import (
    make_season_specific_url, make_current_season_url, url_matches_requested_season, make_cup_url_candidates,
    get_last_page_num, parse_results_page, is_regular_season, rows_fall_in_season, build_team_games, ResultRow,
    parse_game_page_odds
)

# The site's stored odds-format preference: 3 = American ("Money Line") odds
ODDS_FORMAT_STORAGE_KEY = "op_oddsFormatId"
AMERICAN_ODDS_FORMAT = "3"
GAME_ROW_SELECTOR = 'a[href*="/basketball/h2h/"]'
FULL_PAGE_MIN_ROWS = 40  # a full results page holds 50 games (+1 pinned)


class OddsPortalScraper:
    """
    Scraper for OddsPortal NBA moneyline data, including the Selenium
    browser automation its JavaScript-rendered pages need.
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 1: BROWSER                            #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def init_driver(self):
        if self.driver is not None:
            return self.driver
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
        # Skip images and fonts for faster loading
        options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.fonts": 2,
        })
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(1400, 1000)
        return self.driver

    def quit_driver(self):
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

    def _row_signature(self) -> tuple:
        """The game links currently shown - changes when a new page has rendered.
        Read in one in-page call: the rows re-render while a page settles, so
        reading them element by element can hit one that's already gone."""
        return tuple(self.driver.execute_script(
            "return Array.from(document.querySelectorAll(arguments[0])).map(a => a.getAttribute('href'))",
            GAME_ROW_SELECTOR))

    def _wait_for_rows(self, previous: tuple = (), timeout: float = 30) -> tuple:
        """Wait until the game rows differ from `previous` and have stopped
        changing (3 identical polls), so a page isn't read mid-render."""
        start, last, stable = time.time(), None, 0
        while time.time() - start < timeout:
            current = self._row_signature()
            if current and current != previous and current == last:
                stable += 1
                if stable >= 3:
                    return current
            else:
                stable = 0
            last = current
            time.sleep(0.5)
        raise TimeoutError(f"results didn't finish rendering within {timeout}s")

    def open_results_page(self, url: str) -> str:
        """
        Load a results page fresh in American odds, and return its HTML.
        The odds format is a site preference kept in the browser's local
        storage, so it's set on the site's origin and then the page is
        loaded again to apply it.
        """
        self.init_driver()
        self.driver.get(url)
        if self.driver.execute_script(f"return localStorage.getItem('{ODDS_FORMAT_STORAGE_KEY}')") != AMERICAN_ODDS_FORMAT:
            self.driver.execute_script(f"localStorage.setItem('{ODDS_FORMAT_STORAGE_KEY}', '{AMERICAN_ODDS_FORMAT}')")
            self.driver.get(url)
        self._wait_for_rows()
        self._dismiss_cookie_consent()
        return self.driver.page_source

    def _dismiss_cookie_consent(self):
        """Close the OneTrust cookie banner (declining) if it's showing."""
        try:
            buttons = self.driver.find_elements(By.ID, "onetrust-reject-all-handler")
            if buttons and buttons[0].is_displayed():
                buttons[0].click()
                time.sleep(1)
        except Exception:
            pass

    def go_to_page(self, page_num: int) -> str:
        """Switch the open results page to another page of results, in-app.
        (A fresh load always shows page 1, so pages aren't reachable by URL.)"""
        before = self._row_signature()
        self.driver.execute_script(f"location.hash = 'page/{page_num}'")
        self._wait_for_rows(previous=before)
        return self.driver.page_source

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 2: RESILIENT PAGE FETCH               #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def _fetch_page(self, url: str, page_num: int, is_last_page: bool,
                   max_attempts: int = 3) -> Optional[List[ResultRow]]:
        """
        One results page's rows, retrying up to max_attempts. A page only
        counts as good if it parses (American odds) and, unless it's the last
        page (which holds just the remainder), shows a full page of games.
        Returns None if every attempt failed.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                html = self.open_results_page(url) if (page_num == 1 or attempt > 1) else None
                if page_num > 1:
                    html = self.go_to_page(page_num)
                rows = parse_results_page(html)
                if not is_last_page and len(rows) < FULL_PAGE_MIN_ROWS:
                    raise RuntimeError(f"only {len(rows)} games rendered")
                return rows, html
            except Exception as e:
                print(f"  ⚠️  Attempt {attempt}/{max_attempts} failed for page {page_num} "
                      f"({e.__class__.__name__}: {e}), retrying...")
        return None

    def _cached_or_fetched(self, cache_path: Optional[str], fetch) -> Optional[List[ResultRow]]:
        """Rows from the cache if this page succeeded on an earlier run, else
        fetch it live and cache it only if it passed its checks - a bad page
        must never be locked in for re-runs."""
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                return parse_results_page(f.read())
        result = fetch()
        if result is None:
            return None
        rows, html = result
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html)
        return rows

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
    #   SECTION 3: SEASON-LEVEL ORCHESTRATION         #
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

    def _resolve_season_url(self, season_start_year: int) -> tuple:
        """The season's results URL - its own archive, or the generic current-
        results page if it isn't archived yet (true for whichever season most
        recently finished, until a newer one starts) - and its page count."""
        url = make_season_specific_url(season_start_year)
        html = self.open_results_page(url)
        if not url_matches_requested_season(self.driver.current_url, season_start_year):
            print(f"  ℹ️  {season_start_year}-{(season_start_year+1)%100:02d} isn't archived under its own "
                  f"OddsPortal URL yet - using the generic current-results page.")
            url = make_current_season_url()
            html = self.open_results_page(url)
        return url, get_last_page_num(html)

    def _scrape_cup_knockouts(self, season_start_year: int, cache_dir: Optional[str]) -> List[ResultRow]:
        """The in-season tournament's quarterfinals and semifinals, which
        OddsPortal lists under a separate competition (see parser.py)."""
        cache_path = os.path.join(cache_dir, "cup.html") if cache_dir else None
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                rows = parse_results_page(f.read())
        else:
            rows = None
            for url in make_cup_url_candidates(season_start_year):
                try:
                    html = self.open_results_page(url)
                except Exception:
                    continue  # no such edition page
                candidate = parse_results_page(html)
                if rows_fall_in_season(candidate, season_start_year):
                    rows = candidate
                    if cache_path:
                        os.makedirs(cache_dir, exist_ok=True)
                        with open(cache_path, "w", encoding="utf-8") as f:
                            f.write(html)
                    break
            if rows is None:
                raise RuntimeError(f"couldn't find OddsPortal's NBA Cup page for {season_start_year}-"
                                   f"{(season_start_year+1)%100:02d}")
        knockouts = [r for r in rows if is_regular_season(r)]  # the final is under "- Play Offs"
        print(f"  🏆 NBA Cup: {len(knockouts)} quarterfinal/semifinal games")
        return knockouts

    def _fill_missing_odds(self, rows: List[ResultRow]):
        """For played games the results page lists without odds, take the
        average of the bookmakers on the game's own page. Rows it can't fill
        stay without odds (build_team_games skips them, and Step 2 flags it)."""
        for row in rows:
            if row.home_odds is not None or row.home_score is None or not row.link:
                continue
            odds = None
            try:
                self.driver.get("https://www.oddsportal.com" + row.link)
                # Wait for the bookmaker lines to render rather than a fixed pause
                deadline = time.time() + 20
                while odds is None and time.time() < deadline:
                    time.sleep(1)
                    odds = parse_game_page_odds(self.driver.find_element(By.TAG_NAME, "body").text)
            except Exception as e:
                print(f"  ⚠️  Couldn't read {row.home} vs {row.away}'s game page ({e.__class__.__name__})")
            if odds:
                row.home_odds, row.away_odds = odds
                print(f"  → {row.home} vs {row.away} ({row.listed_date}): no odds on the results page; "
                      f"averaged its game page's bookmakers: {odds[0]:+d} / {odds[1]:+d}")
            else:
                print(f"  ⚠️  {row.home} vs {row.away} ({row.listed_date}): no odds on its game page either")

    def scrape_season(self, season_start_year: int, cache_dir: Optional[str] = None) -> Dict[str, List[TeamGame]]:
        """
        Every regular-season game of the season, as per-team games (see
        parser.build_team_games). cache_dir: if given, each page's HTML is cached
        there once it passes its checks, so a re-run after a mid-scrape
        failure (e.g. OddsPortal rate-limiting) resumes where it left off.
        """
        rows: List[ResultRow] = []
        consecutive_failures = 0
        MAX_CONSECUTIVE_PAGE_FAILURES = 3

        self.init_driver()
        try:
            url, last_page = self._resolve_season_url(season_start_year)
            for page_num in range(1, last_page + 1):
                print(f"Scraping page {page_num}/{last_page}...")
                cache_path = os.path.join(cache_dir, f"page_{page_num}.html") if cache_dir else None
                page_rows = self._cached_or_fetched(
                    cache_path, lambda: self._fetch_page(url, page_num, is_last_page=(page_num == last_page)))
                if page_rows is None:
                    # Several pages in a row failing even after retries points
                    # to something systemic (rate-limiting, or the site changed)
                    # - stop rather than produce a complete-looking partial season
                    consecutive_failures += 1
                    print(f"  ❌ Page {page_num} failed after retries")
                    if consecutive_failures >= MAX_CONSECUTIVE_PAGE_FAILURES:
                        raise RuntimeError(
                            f"{consecutive_failures} consecutive pages failed to load even after retries "
                            f"(most recently page {page_num}/{last_page}). OddsPortal is probably rate-limiting "
                            f"or blocking automated requests, or its site changed - aborting rather than "
                            f"producing an incomplete dataset. Wait a while before retrying.")
                    continue
                consecutive_failures = 0
                regular = [r for r in page_rows if is_regular_season(r)]
                print(f"  → {len(regular)} regular-season games listed")
                rows.extend(regular)

            if season_start_year >= FIRST_IST_SEASON:
                rows.extend(self._scrape_cup_knockouts(season_start_year, cache_dir))
            self._fill_missing_odds(rows)
        finally:
            self.quit_driver()

        games = build_team_games(rows, season_start_year)
        team_rows = sum(len(g) for g in games.values())
        print(f"\n{'='*60}")
        print(f"Total games scraped: {team_rows // 2}")
        print(f"Total team-game rows (2 per game): {team_rows}")
        print(f"(Step 2 checks these against the expected counts)")
        print(f"{'='*60}\n")
        return games


def scrape_season(season: int, cache_dir: Optional[str] = None, headless: bool = False) -> Dict[str, List[TeamGame]]:
    """Entry point: every regular-season game of the season from OddsPortal, as
    each team's games in date order (see OddsPortalScraper.scrape_season)."""
    return OddsPortalScraper(headless=headless).scrape_season(season, cache_dir=cache_dir)
