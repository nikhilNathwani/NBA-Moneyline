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

### Running the Scraper

```bash
# Navigate to scrape folder
cd data

# Activate virtual environment
source .venv/bin/activate

# Run scraper for specific season
python3 main.py --seasons 2025

# Run in headless mode (no browser window)
python3 main.py --seasons 2025 --headless

# Scrape multiple seasons
python3 main.py --seasons 2024 2025

# When done, deactivate venv (optional)
deactivate
```

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
