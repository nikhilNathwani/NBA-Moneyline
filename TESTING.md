# Testing Checklist - NBA Moneyline

After making configuration changes, verify everything still works.

## ✅ Web App Tests

### Test 1: Local Development Server

```bash
cd /path/to/NBA\ Moneyline
npm run dev
```

**Expected:** Server starts on http://localhost:3000

### Test 2: Frontend Loads

- Open http://localhost:3000 in browser
- **Expected:** Page loads, no console errors
- **Expected:** Season dropdown appears
- **Expected:** Team filters visible

### Test 3: API Endpoints

```bash
# Test result summary endpoint
curl "http://localhost:3000/api/result-summary?seasonStartYear=2024&team=Lakers"
```

**Expected:** JSON response with Lakers data

### Test 4: Database Connection

```bash
# From db-testing folder
cd db-testing
python3 query_db.py
```

**Expected:** Query results print successfully

## ✅ Python Scraper Tests

### Test 1: Virtual Environment

```bash
cd data
source .venv/bin/activate
python3 --version
pip list
```

**Expected:** Python version shows, packages listed

### Test 2: Import Test (No Scraping)

```bash
cd data
source .venv/bin/activate
python3 -c "from scrape.odds.scraper import OddsPortalScraper; print('✅ Imports work')"
```

**Expected:** "✅ Imports work" prints

### Test 3: Database Connection Test

```bash
cd data
source .venv/bin/activate
python3 -c "from publish.migrate_to_production import get_postgres_connection; conn = get_postgres_connection(); print('✅ DB connected'); conn.close()"
```

**Expected:** "✅ DB connected" prints

### Test 4: Dry Run Help

```bash
cd data
source .venv/bin/activate
python3 main.py --help
```

**Expected:** Help text displays all options

## ✅ Production Safety

### Don't Test (Would Break Production)

- ❌ Don't run full scraper (would modify production DB)
- ❌ Don't commit test data
- ❌ Don't push to main branch yet

### Safe to Test

- ✅ Local web server (reads from production DB, doesn't write)
- ✅ Import tests (no side effects)
- ✅ Database queries (read-only)

## 🔒 Pre-Deployment Checklist

Before pushing changes:

- [ ] All tests above pass
- [ ] .venv/ is in .gitignore
- [ ] .env.development.local not committed
- [ ] package.json has correct dependencies
- [ ] requirements.txt organized and committed
- [ ] No temporary test files committed
