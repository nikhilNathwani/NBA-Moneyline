"""
Shared filesystem paths for the NBA Moneyline data pipeline.
"""

import os

# The project root (parent of data/). Three levels up from this file:
# data/util/paths.py -> data/util -> data -> project root.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
