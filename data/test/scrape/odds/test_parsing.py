"""
Tests for the pure HTML-parsing functions in scrape.odds.parser that
interpret already-fetched OddsPortal HTML: page-quality counting,
row-level odds/winner extraction (with its fallback signal), and
detail-page odds extraction. No network, no Selenium - everything here
takes HTML/BeautifulSoup elements already in hand.
"""

from bs4 import BeautifulSoup

from scrape.odds.parser import (
    countGameDataRows, extractOddsAndWinnerFromRow, RowOddsResult,
    findDetailPageLink, extractOddsFromDetailSoup,
)


def _eventRows(html: str):
    return BeautifulSoup(html, "lxml").find_all(class_="eventRow")


def test_count_game_data_rows_distinguishes_headers_and_game_rows():
    html = '''
    <div class="eventRow"><div data-testid="date-header">Jan 1</div></div>
    <div class="eventRow"><div data-testid="game-row"></div></div>
    <div class="eventRow"><div data-testid="game-row"></div></div>
    <div class="eventRow"></div>
    '''
    non_header_rows, rows_with_game_data = countGameDataRows(_eventRows(html))
    assert non_header_rows == 3  # 4 total rows - 1 date header
    assert rows_with_game_data == 2  # only 2 of those 3 have a game-row testid


def test_extract_odds_and_winner_success():
    html = '''
    <div data-testid="game-row">
      <p class="participant-name">Boston Celtics</p>
      <p class="participant-name">Miami Heat</p>
      <p data-testid="odd-container-winning">-150</p>
      <p data-testid="odd-container-losing">130</p>
    </div>
    '''
    gameRow = BeautifulSoup(html, "lxml").select_one('[data-testid="game-row"]')
    extraction = extractOddsAndWinnerFromRow(gameRow)
    assert extraction.result == RowOddsResult.SUCCESS
    assert extraction.odds == (True, False, -150, 130)


def test_extract_odds_and_winner_needs_fallback_when_odds_missing():
    html = '''
    <div data-testid="game-row">
      <p class="participant-name">Boston Celtics</p>
      <p class="participant-name">Miami Heat</p>
    </div>
    '''
    gameRow = BeautifulSoup(html, "lxml").select_one('[data-testid="game-row"]')
    extraction = extractOddsAndWinnerFromRow(gameRow)
    assert extraction.result == RowOddsResult.NEEDS_FALLBACK
    assert extraction.odds is None


def test_extract_odds_and_winner_parse_error_when_odds_unparseable():
    html = '''
    <div data-testid="game-row">
      <p class="participant-name">Boston Celtics</p>
      <p class="participant-name">Miami Heat</p>
      <p data-testid="odd-container-winning">N/A</p>
      <p data-testid="odd-container-losing">N/A</p>
    </div>
    '''
    gameRow = BeautifulSoup(html, "lxml").select_one('[data-testid="game-row"]')
    extraction = extractOddsAndWinnerFromRow(gameRow)
    assert extraction.result == RowOddsResult.PARSE_ERROR
    assert extraction.error is not None


def test_find_detail_page_link_present():
    row = BeautifulSoup('<div data-testid="game-row"><a href="/game/abc123/">link</a></div>', "lxml")
    assert findDetailPageLink(row) == "/game/abc123/"


def test_find_detail_page_link_absent():
    row = BeautifulSoup('<div data-testid="game-row">no link here</div>', "lxml")
    assert findDetailPageLink(row) is None


def test_extract_odds_from_detail_soup_success_home_win():
    detail_soup = BeautifulSoup(
        '<p data-testid="odd-container">-150</p><p data-testid="odd-container">130</p>', "lxml")
    row = BeautifulSoup('''
        <div data-testid="game-row">
          <div class="font-bold"><p class="participant-name">Boston Celtics</p></div>
          <p class="participant-name">Miami Heat</p>
        </div>
    ''', "lxml")
    assert extractOddsFromDetailSoup(detail_soup, row) == (True, False, -150, 130)


def test_extract_odds_from_detail_soup_not_enough_odds_elements():
    detail_soup = BeautifulSoup('<p data-testid="odd-container">-150</p>', "lxml")
    row = BeautifulSoup('<div data-testid="game-row"></div>', "lxml")
    assert extractOddsFromDetailSoup(detail_soup, row) == (False, False, -1, -1)


def test_extract_odds_from_detail_soup_unparseable_odds():
    detail_soup = BeautifulSoup(
        '<p data-testid="odd-container">N/A</p><p data-testid="odd-container">N/A</p>', "lxml")
    row = BeautifulSoup('<div data-testid="game-row"></div>', "lxml")
    assert extractOddsFromDetailSoup(detail_soup, row) == (False, False, -1, -1)


def test_extract_odds_from_detail_soup_not_enough_participant_names_keeps_odds():
    # Matches existing behavior: winner can't be determined, but valid odds
    # are still returned rather than discarded.
    detail_soup = BeautifulSoup(
        '<p data-testid="odd-container">-150</p><p data-testid="odd-container">130</p>', "lxml")
    row = BeautifulSoup(
        '<div data-testid="game-row"><p class="participant-name">Boston Celtics</p></div>', "lxml")
    assert extractOddsFromDetailSoup(detail_soup, row) == (False, False, -150, 130)
