# src/scraper/hash_navigate_and_save.py
from playwright.sync_api import sync_playwright
from pathlib import Path
from .config import (
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


def save_section_screenshot(page, name: str):
    shot_dir = Path("logs/screenshots")
    shot_dir.mkdir(parents=True, exist_ok=True)
    out = shot_dir / f"section__{name}.png"
    try:
        page.screenshot(path=str(out), full_page=False)
        return out
    except Exception:
        return None


def hash_navigate_and_save():
    ensure_dirs()
    ts = timestamp_for_filename()
    out_filename = f"ticket_attributes_hashnav__{ts}.html"
    log(f"HASH NAV RUN: {ts} -> {out_filename}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)

            log(f"Navigating to base URL: {BASE_URL}")
            page.goto(BASE_URL, timeout=DEFAULT_TIMEOUT_MS)
            page.wait_for_timeout(1200)

            # collect unique in-page hrefs that start with '#'
            anchors = page.query_selector_all('a[href^="#"]')
            hrefs = []
            for a in anchors:
                try:
                    h = a.get_attribute("href")
                except Exception:
                    continue
                if not h or not h.startswith("#"):
                    continue
                if h not in hrefs:
                    hrefs.append(h)

            log(f"Found {len(hrefs)} unique hash anchors.")

            # storage for results
            succeeded = []
            failed = []

            for idx, href in enumerate(hrefs, start=1):
                frag = href.lstrip("#")
                safe_name = frag.replace("/", "_")[:80] or f"frag{idx}"
                log(f"[{idx}/{len(hrefs)}] Setting location.hash = '{href}' (fragment: {frag})")

                # set hash and dispatch event to trigger SPA router
                try:
                    page.evaluate(f"() => {{ window.location.hash = '{href}'; window.dispatchEvent(new HashChangeEvent('hashchange')); }}")
                except Exception as e:
                    log(f"  WARN: failed to set hash for {href}: {e}")

                # give SPA time to react
                page.wait_for_timeout(1200)

                # attempt to wait for element with id equal to fragment (most docs render an element with that id)
                waited = False
                try:
                    sel = f"#{frag}"
                    page.wait_for_selector(sel, timeout=2500)
                    log(f"  OK: selector {sel} appeared.")
                    succeeded.append(href)
                    waited = True
                except Exception:
                    # fallback: wait for any h2 that contains part of the fragment text (case-insensitive)
                    try:
                        maybe_text = frag.replace("_", " ").split()[0][:10]
                        page.wait_for_selector(f"h2:has-text('{maybe_text}')", timeout=1500)
                        log(f"  OK (fallback): found h2 containing '{maybe_text}'")
                        succeeded.append(href)
                        waited = True
                    except Exception:
                        log(f"  TIMEOUT: no selector matched for {href}")

                # if not matched, capture a screenshot for debugging
                if not waited:
                    shot = save_section_screenshot(page, safe_name)
                    log(f"  Screenshot saved for failed fragment {href}: {shot}")
                    failed.append(href)

            # final snapshot
            page.wait_for_timeout(800)
            html = page.content()
            saved = save_html(html, out_filename)
            log(f"Saved final HTML to: {saved}")

            log(f"Hash-nav summary: {len(succeeded)} succeeded, {len(failed)} failed.")
            if failed:
                log("Failed fragments (examples):")
                for f in failed[:20]:
                    log(f"  - {f}")

            browser.close()
            log("Hash-nav run completed.")

    except Exception as ex:
        log(f"ERROR during hash-nav run: {ex}")


if __name__ == "__main__":
    hash_navigate_and_save()
    print("Done hash-nav run.")
