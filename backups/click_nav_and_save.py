# src/scraper/click_nav_and_save.py
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
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)


def save_html(content: str, filename: str):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    file_path = RAW_DIR / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


def click_anchors_and_save():
    ensure_dirs()
    ts = timestamp_for_filename()
    out_filename = f"ticket_attributes_clicked__{ts}.html"
    log(f"DEBUG CLICK RUN: {ts} -> {out_filename}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)

            log(f"Navigating to {BASE_URL}")
            page.goto(BASE_URL, timeout=DEFAULT_TIMEOUT_MS)

            # initial wait
            page.wait_for_timeout(1500)

            # find anchors on the page that look like in-page nav links (href starting with "#")
            anchors = page.query_selector_all('a[href^="#"]')
            log(f"Found {len(anchors)} in-page anchors (href^='#').")

            # To avoid duplicates, build a unique list of hrefs
            hrefs = []
            for a in anchors:
                try:
                    href = a.get_attribute("href")
                    text = (a.inner_text() or "").strip()
                except Exception:
                    continue
                if not href:
                    continue
                if href not in hrefs:
                    hrefs.append(href)

            log(f"{len(hrefs)} unique href anchors to try: {hrefs}")

            # Click each anchor and wait briefly for content to render
            for idx, href in enumerate(hrefs, start=1):
                try:
                    selector = f'a[href="{href}"]'
                    log(f"[{idx}/{len(hrefs)}] Clicking {selector}")
                    page.click(selector, timeout=5000)
                except Exception as e:
                    log(f"Click failed for {href}: {e}")

                # give the SPA time to render content for the clicked section
                page.wait_for_timeout(1200)

                # optionally try waiting for a common content selector (#ticket_attributes or h2)
                try:
                    page.wait_for_selector("#ticket_attributes, h2, .section", timeout=1200)
                except Exception:
                    # it's ok if selector doesn't appear; continue
                    pass

            # final wait & capture
            page.wait_for_timeout(1500)
            html = page.content()
            saved = save_html(html, out_filename)
            log(f"Saved clicked snapshot to: {saved}")

            browser.close()
            log("Click-run completed successfully.")
    except Exception as ex:
        log(f"ERROR during click-run: {ex}")


if __name__ == "__main__":
    click_anchors_and_save()
    print("Done debug click-run.")
