"""
Selenium WebDriver automation utility.

Provides WebDriver functionality for scrapers that need to interact with
dynamic web pages. Handles driver setup, page loading, scrolling, etc.
"""

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


class SeleniumWebDriver:
    """
    Utility class providing Selenium WebDriver automation.
    
    Scrapers that need to interact with dynamic pages can inherit from this
    to get WebDriver capabilities without reimplementing them.
    """
    
    def __init__(self, headless: bool = False):
        """
        Initialize the Selenium WebDriver utility.
        
        Args:
            headless (bool): If True, run Chrome in headless mode
        """
        self.headless = headless
        self.wait_time = 10
        self.driver = None
    
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

        # --- IMPORTANT: Force a TRUE network reload to defeat Vue router caching ---
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
        Click through the OneTrust cookie-consent banner if it's covering the
        page. An instant (non-waiting) check: by the time this is called
        we've already slept after navigation, so the banner - if it's going
        to appear at all - is already in the DOM. Not waiting here avoids
        adding dead latency to every page load in the common case where the
        banner was already dismissed earlier in this browser session.
        """
        try:
            buttons = self.driver.find_elements(By.ID, "onetrust-reject-all-handler")
            if buttons:
                buttons[0].click()
                time.sleep(1)  # let the modal finish closing before we scroll/parse
        except Exception:
            pass  # not present this load - already dismissed, or this page doesn't show it


    def makeSoup(self) -> BeautifulSoup:
        """
        Load a page and return BeautifulSoup object.
        
        Args:
            url (str): URL to load
            wait_selector (str): CSS selector to wait for before parsing (optional)
            
        Returns:
            BeautifulSoup: Parsed HTML content
        """
        html = self.driver.page_source
        return BeautifulSoup(html, "lxml")
    
    # def scrollToBottom(self):
    #     """
    #     Scroll to bottom of page to trigger lazy loading.
        
    #     Useful for pages that load content dynamically as you scroll.
    #     """
    #     if self.driver is None:
    #         raise RuntimeError("Driver not initialized. Call initDriver() first.")
            
    #     last_height = self.driver.execute_script("return document.body.scrollHeight")
    #     while True:
    #         self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    #         time.sleep(1)
            
    #         new_height = self.driver.execute_script("return document.body.scrollHeight")
    #         if new_height == last_height:
    #             break
    #         last_height = new_height

    def scrollToBottom(self):
        """
        Scroll to bottom of page to trigger lazy loading.
        
        Scrolls in increments to ensure lazy-loaded content is triggered.
        Useful for pages that load content dynamically as you scroll.
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
        time.sleep(2) #Additional wait to ensure content is fully loaded

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
