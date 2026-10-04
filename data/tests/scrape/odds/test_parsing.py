"""
Tests for the pure HTML-parsing functions in scrape.odds.parser: page
structure parsing (game rows, pagination), page-quality counting,
row-level odds/winner extraction (with its fallback signal), team-name
extraction, and detail-page odds extraction. No network, no Selenium -
everything here takes raw HTML strings or BeautifulSoup elements already
in hand.
"""

from bs4 import BeautifulSoup

from scrape.odds.parser import (
    getLastPageNum, parseGameRows, countGameDataRows,
    extractGameRowAndTeamNames, extractOddsAndWinnerFromRow, RowOddsResult,
    findDetailPageLink, extractOddsFromDetailHtml,
)


def test_get_last_page_num_finds_last_pagination_link():
    html = '''
    <a class="pagination-link" data-number="1"></a>
    <a class="pagination-link" data-number="2"></a>
    <a class="pagination-link" data-number="7"></a>
    '''
    assert getLastPageNum(html) == 7


def test_get_last_page_num_defaults_to_one_when_no_pagination():
    assert getLastPageNum('<div>no pagination here</div>') == 1


def test_parse_game_rows_finds_all_event_rows():
    html = '''
    <div class="eventRow"><div data-testid="date-header">Jan 1</div></div>
    <div class="eventRow"><div data-testid="game-row"></div></div>
    <div class="not-an-event-row"></div>
    '''
    assert len(parseGameRows(html)) == 2


def test_count_game_data_rows_distinguishes_headers_and_game_rows():
    html = '''
    <div class="eventRow"><div data-testid="date-header">Jan 1</div></div>
    <div class="eventRow"><div data-testid="game-row"></div></div>
    <div class="eventRow"><div data-testid="game-row"></div></div>
    <div class="eventRow"></div>
    '''
    non_header_rows, rows_with_game_data = countGameDataRows(parseGameRows(html))
    assert non_header_rows == 3  # 4 total rows - 1 date header
    assert rows_with_game_data == 2  # only 2 of those 3 have a game-row testid


def test_extract_game_row_and_team_names_success():
    html = '''
    <div data-testid="game-row">
      <p class="participant-name">Boston Celtics</p>
      <p class="participant-name">Miami Heat</p>
    </div>
    '''
    row = BeautifulSoup(html, "lxml")
    gameRow, homeTeamName, awayTeamName = extractGameRowAndTeamNames(row)
    assert gameRow is not None
    assert homeTeamName == "Boston Celtics"
    assert awayTeamName == "Miami Heat"


def test_extract_game_row_and_team_names_no_game_row():
    row = BeautifulSoup('<div data-testid="date-header">Jan 1</div>', "lxml")
    assert extractGameRowAndTeamNames(row) is None


def test_extract_game_row_and_team_names_not_enough_teams():
    row = BeautifulSoup(
        '<div data-testid="game-row"><p class="participant-name">Boston Celtics</p></div>', "lxml")
    assert extractGameRowAndTeamNames(row) is None


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


def test_extract_odds_from_detail_html_success_home_win():
    detail_html = '<p data-testid="odd-container">-150</p><p data-testid="odd-container">130</p>'
    row = BeautifulSoup('''
        <div data-testid="game-row">
          <div class="font-bold"><p class="participant-name">Boston Celtics</p></div>
          <p class="participant-name">Miami Heat</p>
        </div>
    ''', "lxml")
    assert extractOddsFromDetailHtml(detail_html, row) == (True, False, -150, 130)


def test_extract_odds_from_detail_html_not_enough_odds_elements():
    detail_html = '<p data-testid="odd-container">-150</p>'
    row = BeautifulSoup('<div data-testid="game-row"></div>', "lxml")
    assert extractOddsFromDetailHtml(detail_html, row) == (False, False, -1, -1)


def test_extract_odds_from_detail_html_unparseable_odds():
    detail_html = '<p data-testid="odd-container">N/A</p><p data-testid="odd-container">N/A</p>'
    row = BeautifulSoup('<div data-testid="game-row"></div>', "lxml")
    assert extractOddsFromDetailHtml(detail_html, row) == (False, False, -1, -1)


def test_extract_odds_from_detail_html_not_enough_participant_names_keeps_odds():
    # Matches existing behavior: winner can't be determined, but valid odds
    # are still returned rather than discarded.
    detail_html = '<p data-testid="odd-container">-150</p><p data-testid="odd-container">130</p>'
    row = BeautifulSoup(
        '<div data-testid="game-row"><p class="participant-name">Boston Celtics</p></div>', "lxml")
    assert extractOddsFromDetailHtml(detail_html, row) == (False, False, -150, 130)
