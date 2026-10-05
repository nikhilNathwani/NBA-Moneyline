"""
Regenerates tableau/games.csv from the production Postgres database - the file
the Tableau dashboard's data connection reads. Run this after a yearly data
migration (data/main.py) so the dashboard picks up the new season.

    python3 data/load/tableau_csv.py

Then open tableau/NBA Moneyline.twbx (the live connection reads the new file),
add the season to the Season parameter's list, and re-publish to Tableau Public.
See data/README.md.
"""

import csv
import os

import psycopg2
from dotenv import load_dotenv

# Computed here rather than imported from util/constants.py: this runs as a
# standalone script (python3 data/load/tableau_csv.py), where util/ isn't importable
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(ROOT, ".env.development.local"))

OUTPUT = os.path.join(ROOT, "tableau", "games.csv")

# Column aliases and row order here define the exact shape of games.csv the
# workbook expects - don't rename or reorder without re-checking the Tableau
# connection. (Opponent, Game Date and Location were appended on 2026-10-04 and
# aren't used by the dashboard yet; appending new columns is safe.)
# Reads the team_games view: each game from both teams' sides, as the
# dashboard uses it.
QUERY = """
    SELECT
        team            AS "Team",
        seasonstartyear AS "Season Start Year",
        gamenumber      AS "Game Number",
        outcome::text   AS "Outcome",
        winodds         AS "Win Odds",
        loseodds        AS "Lose Odds",
        opponent        AS "Opponent",
        game_date       AS "Game Date",
        CASE is_home WHEN true THEN 'Home' WHEN false THEN 'Away' ELSE 'Neutral' END
                        AS "Location"
    FROM team_games
    ORDER BY team, seasonstartyear, gamenumber
"""


def main():
    conn = psycopg2.connect(os.getenv("POSTGRES_URL"))
    cur = conn.cursor()
    cur.execute(QUERY)
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]
    conn.close()

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
