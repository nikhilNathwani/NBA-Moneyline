# Ensures pytest inserts this directory onto sys.path (matching how main.py
# runs, since it's launched from this directory too), so tests can use the
# same `from scrape.xxx import ...` / `from storage.xxx import ...` /
# `from util.xxx import ...` style imports as the rest of the codebase
# without needing package installation.
