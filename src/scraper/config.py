
# src/scraper/config.py
from pathlib import Path
from datetime import datetime

# Primary URL to fetch
BASE_URL = "https://api.freshservice.com/#ticket_attributes"

# Where to save raw HTML
RAW_DIR = Path("data/raw")

# Logging file
LOG_FILE = Path("logs/fetch_primary_page.log")

# Playwright settings
# Set HEADLESS = False during debugging to see the browser
HEADLESS = False

# Timeout (ms) for Playwright waits / navigation
DEFAULT_TIMEOUT_MS = 60000  # 30 seconds

def ensure_dirs():
    """Create required directories if they don't exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def timestamp_for_filename():
    """Return a compact timestamp string suitable for filenames."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
