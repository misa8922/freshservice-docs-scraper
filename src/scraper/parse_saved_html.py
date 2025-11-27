# src/scraper/parse_saved_html.py
"""
Parse saved Freshservice API HTML snapshots and produce structured JSON outputs.

Outputs:
 - data/clean/<slug>.json   (one file per section/fragment)
 - data/clean/docs.jsonl    (combined JSONL, 1 object per line)

Heuristics:
 - Use anchors (a[href^="#"]) to enumerate fragments.
 - For each fragment '#frag', find an element with id="frag".
 - Extract nearest parent section/div and gather:
    - title (first h1/h2/h3 inside)
    - full HTML of the section (innerHTML)
    - text (cleaned)
    - code blocks (<pre>, <code>)
    - endpoints via regex (GET/POST/PUT/DELETE/PATCH lines)
    - parameter tables (parsed into rows)
"""
import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

ENDPOINT_RE = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\b\s+([^\s'\"<>{}]+)", re.IGNORECASE)

def slugify(s: str) -> str:
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^\w\-_.]", "", s)
    return s[:120].lower() or "section"

def extract_tables(soup_section):
    """Return list of tables as list-of-dicts: {headers: [...], rows: [[...],[...]]}"""
    results = []
    tables = soup_section.find_all("table")
    for table in tables:
        # headers
        headers = []
        thead = table.find("thead")
        if thead:
            ths = thead.find_all("th")
            headers = [th.get_text(strip=True) for th in ths]
        else:
            # try first row as header
            first_row = table.find("tr")
            if first_row:
                headers = [td.get_text(strip=True) for td in first_row.find_all(["th","td"])]
        # rows
        rows = []
        for tr in table.find_all("tr"):
            tds = tr.find_all(["td","th"])
            if not tds:
                continue
            row = [td.get_text(strip=True) for td in tds]
            rows.append(row)
        results.append({"headers": headers, "rows": rows})
    return results

def extract_code_blocks(soup_section):
    codes = []
    # capture <pre>, <code>, and elements with class that indicate code (like .api-code)
    for tag in soup_section.find_all(["pre","code"]):
        txt = tag.get_text()
        codes.append(txt)
    # also look for elements containing class "api-code"
    for el in soup_section.select(".api-code, .code, .example"):
        txt = el.get_text(separator="\n").strip()
        if txt and txt not in codes:
            codes.append(txt)
    return codes

def extract_endpoints(text):
    results = []
    for m in ENDPOINT_RE.finditer(text):
        method = m.group(1).upper()
        path = m.group(2).strip()
        # sanitize common trailing punctuation
        path = path.rstrip(" ,;")
        results.append({"method": method, "path": path})
    return results

def find_section_container(tag):
    # Try to find the nearest ancestor that looks like a section container
    for ancestor in tag.parents:
        if ancestor.name == "section":
            return ancestor
        # common doc container classes
        cls = ancestor.get("class") or []
        if any(c in ("section","api-section","content","doc-section","row") for c in cls):
            return ancestor
    # fallback to the element itself
    return tag

def parse_one_file(html_path: Path):
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(text, "lxml")

    # collect all unique hash anchors from the page (nav links)
    anchors = soup.select('a[href^="#"]')
    hrefs = []
    for a in anchors:
        href = a.get("href")
        if href and href.startswith("#") and href not in hrefs:
            hrefs.append(href)

    # also gather any elements that explicitly have an id (even without nav link)
    ids = [f"#{tag['id']}" for tag in soup.find_all(attrs={"id": True}) if tag.get("id")]
    for idref in ids:
        if idref not in hrefs:
            hrefs.append(idref)

    parsed_items = []

    for href in hrefs:
        frag = href.lstrip("#")
        if not frag:
            continue
        # try to locate an element with that id
        target = soup.find(id=frag)
        if not target:
            # skip silently if not present
            continue
        container = find_section_container(target)
        # extract title: first h1/h2/h3 within container or the anchor text
        title_tag = container.find(["h1","h2","h3"])
        title = title_tag.get_text(strip=True) if title_tag else target.get_text(strip=True) or frag

        # inner HTML and cleaned text
        inner_html = "".join(str(c) for c in container.contents)
        cleaned_text = container.get_text(separator="\n", strip=True)

        # code examples and endpoints
        code_blocks = extract_code_blocks(container)
        endpoints = extract_endpoints(cleaned_text)

        # tables (params etc.)
        tables = extract_tables(container)

        item = {
            "source_file": str(html_path),
            "fragment": frag,
            "title": title,
            "slug": slugify(title or frag),
            "inner_text": cleaned_text,
            "inner_html": inner_html,
            "code_blocks": code_blocks,
            "endpoints": endpoints,
            "tables": tables
        }

        # write each item to a JSON file
        out_filename = CLEAN_DIR / f"{item['slug']}__{frag}.json"
        with open(out_filename, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

        parsed_items.append(item)

    # write combined JSONL
    combined_path = CLEAN_DIR / "docs.jsonl"
    with open(combined_path, "a", encoding="utf-8") as outf:
        for it in parsed_items:
            outf.write(json.dumps({
                "source_file": it["source_file"],
                "fragment": it["fragment"],
                "title": it["title"],
                "slug": it["slug"],
                "inner_text": it["inner_text"],
                "code_blocks": it["code_blocks"],
                "endpoints": it["endpoints"],
                "tables": it["tables"]
            }, ensure_ascii=False) + "\n")

    return parsed_items

def parse_all_raw():
    all_files = sorted(RAW_DIR.glob("*.html"))
    summary = {"files": len(all_files), "sections": 0}
    for f in all_files:
        print(f"Parsing: {f}")
        items = parse_one_file(f)
        print(f"  Extracted {len(items)} sections from {f.name}")
        summary["sections"] += len(items)
    print("Done. Summary:", summary)
    return summary

if __name__ == "__main__":
    parse_all_raw()
