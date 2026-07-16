"""
Frontend update utilities for the NBA Moneyline data pipeline.

Handles updating the seasons list in renderFilters.js and committing changes to git.
"""

import os
import re
import subprocess
from typing import List


def get_render_filters_path() -> str:
    """Get the absolute path to renderFilters.js."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(project_root, 'public', 'js', 'view', 'renderFilters.js')


def read_seasons_list() -> List[str]:
    """Read the current seasons list from renderFilters.js."""
    file_path = get_render_filters_path()
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the seasons array using regex
    pattern = r'const seasons = \[([\s\S]*?)\];'
    match = re.search(pattern, content)
    
    if not match:
        raise ValueError("Could not find seasons array in renderFilters.js")
    
    # Extract season strings
    seasons_text = match.group(1)
    seasons = re.findall(r'"(\d{4}-\d{2})"', seasons_text)
    
    return seasons


def update_seasons_list(new_seasons: List[int]) -> bool:
    """
    Update the seasons list in renderFilters.js with new seasons.
    
    Args:
        new_seasons: List of season start years (e.g., [2024])
        
    Returns:
        True if seasons were added, False if no changes needed
    """
    file_path = get_render_filters_path()
    current_seasons = read_seasons_list()
    
    # Convert new seasons to the format "YYYY-YY"
    formatted_new_seasons = []
    for year in new_seasons:
        season_str = f"{year}-{(year + 1) % 100:02d}"
        if season_str not in current_seasons:
            formatted_new_seasons.append(season_str)
    
    if not formatted_new_seasons:
        return False  # No new seasons to add
    
    # Add new seasons to the list and sort
    all_seasons = sorted(current_seasons + formatted_new_seasons)
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Build the new seasons array string
    seasons_array = 'const seasons = [\n'
    for season in all_seasons:
        seasons_array += f'\t"{season}",\n'
    seasons_array += '];'
    
    # Replace the old seasons array with the new one
    pattern = r'const seasons = \[([\s\S]*?)\];'
    new_content = re.sub(pattern, seasons_array, content)
    
    # Write back to file
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    return True


def commit_and_push_changes(seasons: List[int]) -> bool:
    """
    Commit and push the updated renderFilters.js to git.
    
    Args:
        seasons: List of season start years that were added
        
    Returns:
        True if successful, False otherwise
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    file_path = get_render_filters_path()
    
    try:
        # Stage the file
        subprocess.run(
            ['git', 'add', file_path],
            cwd=project_root,
            check=True,
            capture_output=True
        )
        
        # Check if there are actually changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--exit-code', file_path],
            cwd=project_root,
            capture_output=True
        )
        
        # Exit code 0 means no changes, 1 means there are changes
        if result.returncode == 0:
            # No changes to commit
            return True
        
        # Create commit message
        season_strs = [f"{year}-{(year + 1) % 100:02d}" for year in seasons]
        if len(season_strs) == 1:
            commit_msg = f"Add {season_strs[0]} season to web app"
        else:
            commit_msg = f"Add {', '.join(season_strs)} seasons to web app"
        
        # Commit
        subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            cwd=project_root,
            check=True,
            capture_output=True
        )
        
        # Push
        subprocess.run(
            ['git', 'push'],
            cwd=project_root,
            check=True,
            capture_output=True
        )
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")
        return False
