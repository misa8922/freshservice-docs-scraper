#2
# src/scraper/scrape_fragments_json.py
"""

- Visits url
- Collects fragment ids from #api-content .scroll-spy[id]
- For each fragment:
    - navigates to the hash (location.hash = '#fragmentId')
    - scrolls the fragment into view
    - waits for relevant selectors to appear
    - extracts structured fields:
        - id, section, title, method, request_url, curl, response_json, description, full_text
    - appends one JSON object per fragment to data/clean/scraped_fragments.jsonl
- Logs progress to logs/scrape_fragments.log
"""
import json
import re
import time
import traceback
from pathlib import Path
from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

# Configuration
START_URL = "https://api.freshservice.com/#ticket_attributes"
RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/clean")
LOG_DIR = Path("logs")
OUTPUT_JSONL = OUT_DIR / "scraped_fragments.jsonl"
LOG_FILE = LOG_DIR / "scrape_fragments.log"

# Make directories
RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Timing / retry configuration (conservative for reliability)
NAV_WAIT_SEC = 0.8           # short wait after nav/hash update
RENDER_WAIT_SEC = 1.0        # base wait to allow JS rendering
MAX_RETRIES = 6              # retry attempts per fragment
SCROLL_WAIT_SEC = 0.5        # wait after scroll_into_view
SELECTOR_TIMEOUT_MS = 8000   # playwright wait_for_selector timeout

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def clean_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r'\r\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'[ \t]+', ' ', t)
    return t.strip()

def safe_get_text(soup_elem):
    try:
        return clean_text(soup_elem.get_text(separator="\n", strip=True))
    except Exception:
        return ""

def extract_from_fragment_html(fragment_html: str, fragment_id: str, source_url: str):
    """
    Given HTML for a fragment (string), parse with BeautifulSoup and try to extract structured data.
    Returns a dictionary with fields (some may be empty).
    """
    soup = BeautifulSoup(fragment_html, "html.parser")

    # Title heuristics
    title = ""
    h2 = soup.find(["h2", "h1", "h3"])
    if h2 and h2.get_text(strip=True):
        title = h2.get_text(strip=True)

    # Section 
    section_name = ""
    # try to infer section from the fragment_id
    section_name = fragment_id.split("_")[0] if fragment_id else ""

    # Find request method and url 
    request_url = ""
    try:
        
        method_tag = soup.select_one(".api-url .label") or soup.select_one(".label-get, .label-post, .label-put, .label-delete")
        if method_tag:
            method = method_tag.get_text(strip=True).upper()
        url_tag = soup.select_one(".api-request-url, .api-url .api-request-url, .api-url span.api-request-url")
        if url_tag:
            request_url = url_tag.get_text(strip=True)
        
        if not request_url:
            m = re.search(r'(/api/[^\s"\']+)', fragment_html)
            if m:
                request_url = m.group(1)
    except Exception:
        pass

    # Extract curl code
    curl_code = ""
    try:
        
        pre_candidates = soup.select("pre.highlight.shell, pre.highlight, pre")
        for p in pre_candidates:
            txt = p.get_text("\n", strip=True)
            if "curl" in txt.lower() or "curl -v" in txt.lower():
                curl_code = txt
                break
        # fallback: search code blocks for "curl" substring
        if not curl_code:
            all_text = soup.get_text("\n", strip=True)
            idx = all_text.lower().find("curl")
            if idx != -1:
                
                curl_code = all_text[idx: idx + 800].splitlines()[0:6]
                curl_code = "\n".join(curl_code)
    except Exception:
        pass

    # Extract the response JSON 
    response_json = ""
    try:
        
        resp_pre = soup.select_one(".expand-response-content pre.highlight.json, .expand-response-content pre, pre.highlight.json, pre.json, .api-code-content pre")
        if resp_pre:
            response_json = resp_pre.get_text("\n", strip=True)
        else:
            
            m = re.search(r'(\{\s*"(?:[a-zA-Z0-9_]+)"[\s\S]{10,2000}\})', fragment_html)
            if m:
                response_json = m.group(1)
    except Exception:
        pass

    # Description 
    description = ""
    full_text = ""
    try:
        
        main = soup.select_one(".api-content-main") or soup
        description = safe_get_text(main.find("p")) if main.find("p") else ""
        full_text = safe_get_text(main)
    except Exception:
        full_text = clean_text(soup.get_text("\n", strip=True))

    return {
        "fragment_id": fragment_id,
        "title": title,
        "section": section_name,
        "method": method,
        "request_url": request_url,
        "curl": curl_code,
        "response_json": response_json,
        "description": description,
        "full_text": full_text,
        "source_url": source_url,
        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def gather_fragment_ids(page):
    """
    Collect fragment ids from #api-content .scroll-spy[id] in document order.
    Returns list of ids (strings).
    """
    # Evaluate in page context to get ids in doc order
    script = """
    (() => {
        const out = [];
        const api = document.querySelector('#api-content');
        if (!api) return out;
        // querySelectorAll returns in document order
        const nodes = api.querySelectorAll('.scroll-spy[id]');
        nodes.forEach(n => out.push(n.id));
        return out;
    })();
    """
    try:
        ids = page.evaluate(script)
        if not ids:
            
            ids = page.evaluate("Array.from(document.querySelectorAll('.scroll-spy[id]')).map(n=>n.id)")
        return ids or []
    except Exception:
        return []

def scrape_all_fragments(headless=True, browser_name="chromium"):
    log("START SCRAPE run (headless=%s, browser=%s)" % (headless, browser_name))
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch(headless=headless, args=["--disable-dev-shm-usage"])
        context = browser.new_context()
        page = context.new_page()

        # go to start url
        log("Navigating to start URL: %s" % START_URL)
        page.goto(START_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(RENDER_WAIT_SEC)  # allow initial JS to run

        # Save a copy of initial full HTML for debugging
        try:
            initial_html = page.content()
            raw_initial = RAW_DIR / "initial_snapshot.html"
            raw_initial.write_text(initial_html, encoding="utf-8")
            log("Saved initial snapshot to %s" % raw_initial)
        except Exception as e:
            log("Could not save initial snapshot: %s" % e)

        # collect fragment ids
        fragment_ids = gather_fragment_ids(page)
        log("Found %d fragment IDs" % len(fragment_ids))
        if not fragment_ids:
            log("No fragment ids found — attempting fallback CSS search")
            
            fragment_ids = page.evaluate("Array.from(document.querySelectorAll('[id]')).map(n=>n.id).filter(Boolean)")
            log("Fallback collected %d IDs" % len(fragment_ids))

        
        total = 0
        with open(OUTPUT_JSONL, "w", encoding="utf-8") as outfh:
            # iterate fragments
            for idx, fid in enumerate(fragment_ids, start=1):
                log(f"[{idx}/{len(fragment_ids)}] Processing fragment id: {fid}")
                success = False
                last_html = ""
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        #the hash so the page's navigation logic runs
                        page.evaluate(f"location.hash = '#{fid}'")
                        time.sleep(NAV_WAIT_SEC)

                        #  to scroll the fragment element into view
                        try:
                            page.locator(f"#{fid}").scroll_into_view_if_needed(timeout=SELECTOR_TIMEOUT_MS)
                        except Exception:
                            
                            pass
                        time.sleep(SCROLL_WAIT_SEC + RENDER_WAIT_SEC)

                       
                        frag_selector = f"#{fid}"
                        
                        try:
                            page.wait_for_selector(frag_selector, timeout=SELECTOR_TIMEOUT_MS)
                        except PWTimeoutError:
                            
                            log(f"  attempt {attempt}: fragment element #{fid} not found in DOM")
                            time.sleep(0.5)
                            continue

                        
                        content_found = False
                        inner_html = ""
                        tstart = time.time()
                        while time.time() - tstart < (SELECTOR_TIMEOUT_MS / 1000):
                            
                            inner_html = page.evaluate(f"""
                                (function() {{
                                    const ph = document.getElementById("{fid}");
                                    if (!ph) return "";
                                    // collect this placeholder plus following siblings until next .scroll-spy
                                    let html = "";
                                    html += ph.outerHTML || "";
                                    let node = ph.nextSibling;
                                    while (node) {{
                                        if (node.nodeType === 1) {{
                                            // stop if the next scroll-spy placeholder with id is reached
                                            if (node.classList && node.classList.contains('scroll-spy') && node.id) break;
                                            html += node.outerHTML || node.innerHTML || "";
                                        }}
                                        node = node.nextSibling;
                                    }}
                                    return html;
                                }})();
                            """)
                            if inner_html and ("api-content-main" in inner_html or "api-code" in inner_html or "curl" in inner_html.lower() or "api-request-url" in inner_html):
                                content_found = True
                                break
                            time.sleep(0.4)

                        if not content_found:
                            
                            inner_html = page.evaluate(f"""
                                (function() {{
                                    const el = document.getElementById("{fid}");
                                    return el ? el.outerHTML : "";
                                }})();
                            """)
                            
                        last_html = inner_html or ""
                        if not last_html:
                            log(f"  attempt {attempt}: no HTML captured for #{fid}")
                            time.sleep(0.4)
                            continue

                        
                        try:
                            frag_file = RAW_DIR / f"{fid}__snapshot.html"
                            frag_file.write_text(last_html, encoding="utf-8")
                        except Exception:
                            pass

                        # Extract structured fields from fragment_html
                        record = extract_from_fragment_html(last_html, fid, START_URL)
                        # Basic sanity check: require some text in full_text
                        if not record.get("full_text"):
                            log(f"  attempt {attempt}: extracted empty full_text for #{fid}; retrying")
                            time.sleep(0.5)
                            continue

                        
                        outfh.write(json.dumps(record, ensure_ascii=False) + "\n")
                        outfh.flush()
                        total += 1
                        log(f"  SUCCESS: extracted and saved fragment #{fid}")
                        success = True
                        break

                    except Exception as e:
                        log(f"  attempt {attempt}: Exception while processing #{fid}: {e}")
                        log(traceback.format_exc())
                        time.sleep(0.8)

                if not success:
                    
                    fail_rec = {
                        "fragment_id": fid,
                        "title": "",
                        "section": "",
                        "method": "",
                        "request_url": "",
                        "curl": "",
                        "response_json": "",
                        "description": "",
                        "full_text": "",
                        "source_url": START_URL,
                        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "error": "failed_to_extract_after_retries"
                    }
                    outfh.write(json.dumps(fail_rec, ensure_ascii=False) + "\n")
                    outfh.flush()
                    log(f"  FAILED: could not extract #{fid} after {MAX_RETRIES} attempts")

        # close browser
        browser.close()
        log(f"SCRAPE COMPLETE. Total fragments saved: {total}. Output: {OUTPUT_JSONL}")

if __name__ == "__main__":
    
    try:
        
        scrape_all_fragments(headless=False, browser_name="chromium")
    except Exception as e:
        log("Fatal error during scrape: " + str(e))
        log(traceback.format_exc())
