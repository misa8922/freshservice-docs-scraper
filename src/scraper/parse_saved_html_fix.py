# src/scraper/parse_saved_html_fix.py
#3
"""
Improved parser: reads saved HTML files in data/raw/, finds the api-content container,
then extracts each fragment as its own document by selecting elements with class
'scroll-spy' that have an 'id' attribute. Writes per-fragment JSONL to
data/clean/deduped_docs.jsonl (overwrites safely with backup).
"""
import json
from pathlib import Path
from bs4 import BeautifulSoup
import re
import shutil
import html

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/clean")
OUT_FILE = OUT_DIR / "deduped_docs.jsonl"
BACKUP = OUT_DIR / "deduped_docs.jsonl.bak"

OUT_DIR.mkdir(parents=True, exist_ok=True)

def clean_text(s: str) -> str:
    # basic cleanup: unescape HTML entities, collapse whitespace, strip
    t = html.unescape(s)
    t = re.sub(r'\r\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()

def get_title(elem):
    # prefer h2/h3 inside element, then .api-content-main h2, then id attr
    for tag in ("h2","h3","h1"):
        t = elem.find(tag)
        if t and t.get_text(strip=True):
            return t.get_text(strip=True)
    # if there is a .api-content-main h2 deeper
    main = elem.select_one(".api-content-main h2")
    if main and main.get_text(strip=True):
        return main.get_text(strip=True)
    # else fallback to id attribute or empty
    return elem.get("id") or ""

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = re.sub(r'_{2,}', '_', s)
    return s.strip('_') or "fragment"

def parse_file(path: Path):
    html_text = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html_text, "html.parser")

    api_content = soup.select_one("#api-content")
    if api_content is None:
        # fallback: try body
        api_content = soup.body or soup

    fragments = []
    # find elements with class=scroll-spy and an id
    for elem in api_content.select(".scroll-spy"):
        fid = elem.get("id")
        if not fid:
            continue
        # Extract visible text from that element
        text = elem.get_text(separator="\n", strip=True)
        text = clean_text(text)
        if not text:
            # skip empty fragments
            continue
        title = get_title(elem)
        slug = slugify(title or fid)
        frag = {
            "source_file": str(path),
            "fragment": fid,
            "title": title or fid,
            "slug": slug,
            "text": text
        }
        fragments.append(frag)
    return fragments

def main():
    # Backup old output if exists
    if OUT_FILE.exists():
        shutil.copy2(OUT_FILE, BACKUP)
        print("Backed up existing", OUT_FILE, "to", BACKUP)

    all_count = 0
    with open(OUT_FILE, "w", encoding="utf-8") as outf:
        for raw in sorted(RAW_DIR.glob("*.html")):
            print("Parsing:", raw)
            frags = parse_file(raw)
            print("  fragments found:", len(frags))
            for f in frags:
                outf.write(json.dumps(f, ensure_ascii=False) + "\n")
                all_count += 1

    print("Wrote", all_count, "fragment documents to", OUT_FILE)

if __name__ == "__main__":
    main()
