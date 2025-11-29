#1
# src/scraper/config.py
from pathlib import Path
from datetime import datetime

# Primary URL
BASE_URL = "https://api.freshservice.com/#ticket_attributes"

# saving raw HTML
RAW_DIR = Path("data/raw")

# Log file
LOG_FILE = Path("logs/fetch_primary_page.log")

# Playwright settings

HEADLESS = False

# Timeout (ms) for Playwright waits 
DEFAULT_TIMEOUT_MS = 60000  

def ensure_dirs():
    """Create required directories if they don't exist yet."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def timestamp_for_filename():
    """Return a compact timestamp string suitable for filenames."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
