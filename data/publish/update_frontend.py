"""
Frontend update utilities for the NBA Moneyline data pipeline.

Handles updating the seasons list in renderFilters.js and committing changes to git.
"""

import os
import re
import subprocess
from typing import List

from util.paths import PROJECT_ROOT

SEASONS_ARRAY_PATTERN = r'const seasons = \[([\s\S]*?)\];'


def get_render_filters_path() -> str:
    """Get the absolute path to renderFilters.js."""
    return os.path.join(PROJECT_ROOT, 'public', 'js', 'view', 'renderFilters.js')


def read_seasons_list() -> List[str]:
    """Read the current seasons list from renderFilters.js."""
    file_path = get_render_filters_path()

    with open(file_path, 'r') as f:
        content = f.read()

    # Find the seasons array using regex
    match = re.search(SEASONS_ARRAY_PATTERN, content)

    if not match:
        raise ValueError("Could not find seasons array in renderFilters.js")

    # Extract season strings
    seasons_text = match.group(1)
    seasons = re.findall(r'"(\d{4}-\d{2})"', seasons_text)

    return seasons


def update_seasons_list(new_season: int) -> bool:
    """
    Update the seasons list in renderFilters.js with the new season.

    Args:
        new_season: Season start year (e.g. 2024)

    Returns:
        True if the season was added, False if it was already present
    """
    file_path = get_render_filters_path()
    current_seasons = read_seasons_list()

    season_str = f"{new_season}-{(new_season + 1) % 100:02d}"
    if season_str in current_seasons:
        return False  # Already present, no change needed

    all_seasons = sorted(current_seasons + [season_str])
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Build the new seasons array string
    seasons_array = 'const seasons = [\n'
    for season in all_seasons:
        seasons_array += f'\t"{season}",\n'
    seasons_array += '];'
    
    # Replace the old seasons array with the new one
    new_content = re.sub(SEASONS_ARRAY_PATTERN, seasons_array, content)
    
    # Write back to file
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    return True


def commit_and_push_changes(season: int) -> bool:
    """
    Commit and push the updated renderFilters.js to git.

    Args:
        season: Season start year that was added

    Returns:
        True if successful, False otherwise
    """
    file_path = get_render_filters_path()

    try:
        # Stage the file
        subprocess.run(
            ['git', 'add', file_path],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True
        )

        # Check if there are actually changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--exit-code', file_path],
            cwd=PROJECT_ROOT,
            capture_output=True
        )
        
        # Exit code 0 means no changes, 1 means there are changes
        if result.returncode == 0:
            # No changes to commit
            return True
        
        # Create commit message
        season_str = f"{season}-{(season + 1) % 100:02d}"
        commit_msg = f"Add {season_str} season to web app"
        
        # Commit
        subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True
        )
        
        # Push
        subprocess.run(
            ['git', 'push'],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True
        )
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")
        return False
