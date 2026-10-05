"""
Pure URL-construction and HTML-parsing functions for the OddsPortal
scraper: everything parameterized purely by its arguments, no live driver
access, which is what makes it independently unit-testable (see
test_urls.py, test_parsing.py) without any Selenium setup.

Written for OddsPortal's site as redesigned in 2026. A results page lists
games newest first under date headers ("08 Dec 2023", or "17 Jun 2024 -
Play Offs" for a stage other than the regular season). Each game is a row
holding a link to the matchup (/basketball/h2h/...) whose text reads:

    status | short status | home score | home team | - | away team | away score | home odds | away odds

e.g. "Finished|FIN|112|Portland Trail Blazers|-|Dallas Mavericks|125|+375|-500".
The link ends in the game's id ("#Yg2RY6Cj"). Each page also pins one game
from elsewhere (anywhere in the list); its link has no id, which is how it's
recognized and skipped.
Odds are read in American format (the scraper sets the site's odds-format
preference); anything else raises, so a format change can't slip through
as wrong numbers.

The pages' data feed is encrypted, deliberately - this only reads what the
page displays.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from util.game import Game

BASE = "https://www.oddsportal.com/basketball/usa"
DATE_HEADER = re.compile(r"^(\d{1,2} [A-Z][a-z]{2} \d{4})\s*(?:-\s*(.+))?$")
AMERICAN_ODDS = re.compile(r"^[+-]\d+$")
SCORE = re.compile(r"^\d+$")


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#   URLS                                          #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

# OddsPortal only gives a season its own archived results URL once a newer
# season has started; the most recently completed season is only reachable
# via the generic (season-agnostic) "current results" URL until then. Both
# are needed - see _resolveSeasonUrl in scraper.py, which checks which one
# applies rather than hardcoding an assumption that breaks as soon as a new
# season starts. Pages beyond the first are reached in-app (see scraper.py),
# not by URL.

def makeSeasonSpecificUrl(seasonStartYear: int) -> str:
    return f"{BASE}/nba-{seasonStartYear}-{seasonStartYear + 1}/results/"


def makeCurrentSeasonUrl() -> str:
    return f"{BASE}/nba/results/"


def urlMatchesRequestedSeason(url: str, seasonStartYear: int) -> bool:
    """Whether a (possibly redirected-to) URL is still the requested season's archive."""
    return f"nba-{seasonStartYear}-{seasonStartYear + 1}" in url


# The in-season tournament's knockout rounds (quarterfinals, semifinals and
# the final) aren't on the NBA results pages at all - OddsPortal files them
# under a separate competition, archived per edition under names that vary
# by year, with the latest edition at the generic "nba-cup" URL. The
# quarterfinals and semifinals count toward the regular season; the final
# doesn't (it's listed under a "- Play Offs" header, so the regular-season
# filter drops it).
def makeCupUrlCandidates(seasonStartYear: int) -> List[str]:
    return [f"{BASE}/nba-cup-{seasonStartYear}/results/",
            f"{BASE}/nba-in-season-tournament-{seasonStartYear}/results/",
            f"{BASE}/nba-cup/results/"]


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#   PAGE PARSING                                  #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

@dataclass
class ResultRow:
    """One game as listed on a results page."""
    listed_date: Optional[date]  # OddsPortal's date (its timezone: evening US games can show a day later)
    stage: str                   # "" for the regular season, else e.g. "Play Offs"
    home: str
    away: str
    home_score: Optional[int]    # None if the game wasn't played (postponed etc.)
    away_score: Optional[int]
    home_odds: Optional[int]     # None if the page shows no odds
    away_odds: Optional[int]
    status: str                  # e.g. "Finished", "After OT"
    event_id: str = ""           # OddsPortal's id for the game (from its link)
    link: str = ""               # the game's page, for the missing-odds fallback


def getLastPageNum(html: str) -> int:
    """The highest page-number button on a results page (1 if none)."""
    soup = BeautifulSoup(html, "lxml")
    numbers = [int(b.get_text(strip=True)) for b in soup.find_all("button")
               if b.get_text(strip=True).isdigit()]
    return max(numbers, default=1)


def _parseOdds(token: str) -> Optional[int]:
    if token in ("-", ""):
        return None
    if not AMERICAN_ODDS.match(token):
        raise ValueError(f"odds {token!r} aren't in American format - did the odds-format setting change?")
    return int(token)


def parseRowText(tokens: List[str]) -> Optional[dict]:
    """Interpret one row's text pieces; None if it isn't a recognizable game row."""
    separators = [i for i, t in enumerate(tokens) if t == "-" and 0 < i < len(tokens) - 1
                  and not SCORE.match(tokens[i - 1]) and not SCORE.match(tokens[i + 1])]
    if not separators:
        return None
    i = separators[0]
    home, away = tokens[i - 1], tokens[i + 1]
    home_score = int(tokens[i - 2]) if i >= 2 and SCORE.match(tokens[i - 2]) else None
    after = tokens[i + 2:]
    away_score = int(after[0]) if after and SCORE.match(after[0]) else None
    if away_score is not None:
        after = after[1:]
    odds = [_parseOdds(t) for t in after[:2]] + [None, None]
    return dict(home=home, away=away, home_score=home_score, away_score=away_score,
                home_odds=odds[0], away_odds=odds[1], status=tokens[0] if tokens else "")


def parseResultsPage(html: str) -> List[ResultRow]:
    """Every game row on a results page, in page order, with the date header above it."""
    soup = BeautifulSoup(html, "lxml")
    rows, header = [], None
    for el in soup.find_all(True):
        if el.name == "a" and "/basketball/h2h/" in (el.get("href") or ""):
            if "#" not in el["href"]:
                continue  # the pinned game: no game id in its link (see module docstring)
            parsed = parseRowText(el.parent.get_text("|", strip=True).split("|"))
            if parsed:
                listed, stage = header if header else (None, "")
                rows.append(ResultRow(listed_date=listed, stage=stage,
                                      event_id=el["href"].rsplit("#", 1)[-1], link=el["href"], **parsed))
        elif el.string:
            match = DATE_HEADER.match(el.string.strip())
            if match:
                header = (datetime.strptime(match.group(1), "%d %b %Y").date(), (match.group(2) or "").strip())
    return rows


def americanToDecimal(odds: int) -> float:
    return 1 + odds / 100 if odds > 0 else 1 + 100 / -odds


def decimalToAmerican(decimal_odds: float) -> int:
    return round((decimal_odds - 1) * 100) if decimal_odds >= 2 else round(-100 / (decimal_odds - 1))


def parseGamePageOdds(page_text: str) -> Optional[tuple]:
    """
    (home odds, away odds) averaged across the bookmakers listed on a game's
    own page, from its visible text - the fallback for a game the results
    page lists without odds. Each bookmaker's line shows its two moneyline
    odds in order (home, away); they're averaged as decimal odds, as
    OddsPortal does, then converted back to American. None if no bookmaker
    lines are found.
    """
    start, end = page_text.find("Bookmakers"), page_text.find("My coupon")
    section = page_text[start:end] if start >= 0 and end > start else ""
    odds = [int(t) for t in re.findall(r"(?m)^[+-]\d+$", section)]
    pairs = list(zip(odds[0::2], odds[1::2]))
    if not pairs or len(odds) % 2:
        return None
    return tuple(decimalToAmerican(sum(americanToDecimal(p[side]) for p in pairs) / len(pairs))
                 for side in (0, 1))


def isRegularSeason(row: ResultRow) -> bool:
    """Regular-season games are listed under a plain date header; other stages add
    " - <stage>". A row above any header can't be classified, so it doesn't count."""
    return row.listed_date is not None and row.stage == ""


def rowsFallInSeason(rows: List[ResultRow], seasonStartYear: int) -> bool:
    """Whether every dated row falls within the season (Sep 1 to Aug 31) - used to
    confirm a generic URL (e.g. the latest NBA Cup edition) is the requested season's."""
    start, end = date(seasonStartYear, 9, 1), date(seasonStartYear + 1, 8, 31)
    dated = [r.listed_date for r in rows if r.listed_date]
    return bool(dated) and all(start <= d <= end for d in dated)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #
#   ROWS -> PER-TEAM GAMES                        #
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ #

def buildTeamGames(rows: List[ResultRow], seasonStartYear: int) -> Dict[str, List[Game]]:
    """
    Turn scraped rows into the pipeline's per-team games: two Game records
    per game (one from each side), each team's games in date order and
    numbered 1..N.

    Skips (with a printed reason) rows that weren't played or show no odds,
    and drops any repeat of the same game (by its OddsPortal id), in case a
    game is ever listed twice.
    Listing order breaks ties within a date (a team never plays twice in one).
    """
    games: Dict[str, List[Game]] = {}
    seen = set()
    for row in rows:
        key = row.event_id or (row.listed_date, row.home, row.away)
        if key in seen:
            continue
        seen.add(key)
        if row.home_score is None or row.away_score is None:
            print(f"  ⚠️  Skipping {row.home} vs {row.away} ({row.listed_date}): no final score ({row.status})")
            continue
        if row.home_odds is None or row.away_odds is None:
            print(f"  ⚠️  Skipping {row.home} vs {row.away} ({row.listed_date}): no odds listed")
            continue
        home_won = row.home_score > row.away_score
        for team, opponent, won, win_odds, lose_odds in (
                (row.home, row.away, home_won, row.home_odds, row.away_odds),
                (row.away, row.home, not home_won, row.away_odds, row.home_odds)):
            game = Game(team, opponent, won, win_odds, lose_odds, seasonStartYear,
                        listedDate=row.listed_date)
            games.setdefault(team, []).append(game)

    for team_games in games.values():
        # Pages list newest first; reverse to oldest first, then a stable sort
        # by date puts rows from separate pages (e.g. the NBA Cup page) in place
        team_games.reverse()
        team_games.sort(key=lambda g: g.listedDate or date.min)
        for n, game in enumerate(team_games, start=1):
            game.gameNumber = n
    return games
