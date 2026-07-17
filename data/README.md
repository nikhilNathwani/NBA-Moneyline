# NBA Moneyline Scraper

Python scripts for scraping NBA moneyline data from OddsPortal.

## Setup

### First Time Setup

```bash
cd data

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**If `.venv/bin/pip` (or pytest, etc.) fails with "cannot execute" / "No such file or directory":**
the venv's wrapper scripts embed an absolute path to this folder at creation time, so moving or
renaming `data/` (or its parent) breaks them. Recreate it:

```bash
cd data
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Scraper

```bash
# Navigate to scrape folder
cd data

# Activate virtual environment
source .venv/bin/activate

# Run scraper for a specific season
python3 main.py --season 2025

# Run in headless mode (no browser window)
python3 main.py --season 2025 --headless

# When done, deactivate venv (optional)
deactivate
```

One season per run, by design - catching up multiple seasons after a gap means running
this multiple times (one invocation per season), not passing several seasons to one run.
See the note at the top of `main.py` for why.

See [YEARLY_WORKFLOW.md](YEARLY_WORKFLOW.md) for detailed annual update process.

## Adding Python Packages

```bash
cd data
source .venv/bin/activate
pip install new-package
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Add new-package"
```

## Dependencies

See [requirements.txt](requirements.txt) for full list. Main dependencies:

- `beautifulsoup4` - HTML parsing
- `selenium` - Browser automation
- `psycopg2-binary` - PostgreSQL connection
- `python-dotenv` - Environment variables

## Environment Variables

The scraper reads from `/.env.development.local` (project root) for database credentials.
