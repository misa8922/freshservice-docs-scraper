# src/scraper/fetch_primary_page.py

from playwright.sync_api import sync_playwright
from pathlib import Path
from ..src.scraper.config import (
    BASE_URL,
    RAW_DIR,
    LOG_FILE,
    HEADLESS,
    DEFAULT_TIMEOUT_MS,
    ensure_dirs,
    timestamp_for_filename
)


def log(message: str):
    """Append a line to the log file and also print."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = message
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def save_html(content: str, filename: str):
    """Save rendered HTML to data/raw/ folder."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    file_path = RAW_DIR / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


def save_screenshot(page, filename: str):
    """Save a screenshot for debugging. Avoid full-page screenshots on extremely tall pages."""
    shot_dir = Path("logs/screenshots")
    shot_dir.mkdir(parents=True, exist_ok=True)
    out = shot_dir / filename

    try:
        # Try to get total page height (may fail in some cases)
        try:
            total_height = page.evaluate("() => document.body.scrollHeight")
        except Exception:
            total_height = None

        # If the page is extremely tall, avoid full_page screenshot (which can crash)
        if total_height and total_height > 120000:  # threshold in pixels (adjustable)
            # set a reasonable viewport and take a viewport-only screenshot
            try:
                page.set_viewport_size({"width": 1200, "height": 900})
            except Exception:
                # ignore viewport sizing errors
                pass
            page.screenshot(path=str(out), full_page=False)
        else:
            # Attempt full-page screenshot for normal-sized pages
            try:
                page.screenshot(path=str(out), full_page=True)
            except Exception:
                # fallback to viewport-only screenshot if full-page fails
                try:
                    page.set_viewport_size({"width": 1200, "height": 900})
                except Exception:
                    pass
                page.screenshot(path=str(out), full_page=False)

        return out
    except Exception as exc:
        # Log the failure but don't raise — we want the scraper to continue and save HTML
        log(f"WARNING: Failed to save screenshot ({filename}): {exc}")
        return None



def scroll_full_page(page, steps: int = 12, pause_ms: int = 600):
    """Scroll down the page in steps to trigger lazy-loaded content."""
    # Get total height from the page
    total_height = page.evaluate("() => document.body.scrollHeight")
    log(f"Page total scrollHeight: {total_height}")
    # Compute step size
    step = max(1, int(total_height // steps))
    y = 0
    while y < total_height:
        page.evaluate(f"() => window.scrollTo(0, {y})")
        page.wait_for_timeout(pause_ms)
        y += step
    # final scroll to bottom
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(pause_ms)
    # give network some time
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        # networkidle may timeout; that's okay
        pass


def fetch_primary_page():
    """Fetch the ticket_attributes page using Playwright, scroll to load dynamic content, take screenshot and save rendered HTML."""
    ensure_dirs()

    timestamp = timestamp_for_filename()
    output_filename = f"ticket_attributes__{timestamp}.html"
    screenshot_filename = f"ticket_attributes__{timestamp}.png"

    log(f"\n=== Fetch Run at {timestamp} ===")
    log(f"URL: {BASE_URL}")
    log(f"HEADLESS: {HEADLESS}, TIMEOUT_MS: {DEFAULT_TIMEOUT_MS}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS)
            page = browser.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)

            log("Navigating to page...")
            page.goto(BASE_URL, timeout=DEFAULT_TIMEOUT_MS)

            # Wait for a key selector to ensure the initial content is present
            try:
                page.wait_for_selector("#ticket_attributes", timeout=10000)
                log("Found selector #ticket_attributes")
            except Exception:
                log("Did not find #ticket_attributes within 10s; continuing anyway.")

            # Do incremental scrolling to trigger lazy loading
            log("Beginning incremental scroll to load dynamic content...")
            scroll_full_page(page, steps=16, pause_ms=600)
            log("Scrolling complete. Taking screenshot...")

            # Save screenshot for debugging
            shot_path = save_screenshot(page, screenshot_filename)
            log(f"Saved screenshot to: {shot_path}")

            # Final small wait and capture HTML
            page.wait_for_timeout(1500)
            html = page.content()

            saved_path = save_html(html, output_filename)
            log(f"Saved HTML to: {saved_path}")
            log("Fetch completed successfully.")

            browser.close()

    except Exception as e:
        err_msg = f"ERROR during fetch: {str(e)}"
        log(err_msg)
        print(err_msg)


if __name__ == "__main__":
    fetch_primary_page()
    print("Done fetching page.")
