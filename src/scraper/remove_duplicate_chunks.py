# src/scraper/remove_duplicate_chunks.py
#5
"""
Remove exact-duplicate chunk texts (byte-for-byte identical) and write a fresh
data/clean/deduped_chunks.jsonl (backing up the previous one if present).
Also prints a short summary.
"""
import json, glob, hashlib, shutil, os
from pathlib import Path

CHUNKS_DIR = Path("data/clean/chunks")
OUT_JSONL = Path("data/clean/deduped_chunks.jsonl")
BACKUP = Path("data/clean/deduped_chunks.jsonl.bak")

def main():
    if not CHUNKS_DIR.exists():
        print("Chunks folder not found:", CHUNKS_DIR)
        return

    # Backup existing deduped jsonl if present
    if OUT_JSONL.exists():
        print("Backing up existing", OUT_JSONL, "to", BACKUP)
        shutil.copy2(OUT_JSONL, BACKUP)

    seen = {}
    total = 0
    unique = 0

    with open(OUT_JSONL, "w", encoding="utf-8") as outf:
        for path in sorted(CHUNKS_DIR.glob("*.json")):
            total += 1
            try:
                j = json.load(open(path, "r", encoding="utf-8"))
            except Exception as e:
                print("Skipping unreadable file:", path, e)
                continue
            text = (j.get("text") or "").strip()
            if not text:
                # keep empty ones if you want, but skip here
                continue
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if h in seen:
                seen[h]["files"].append(str(path))
                continue
            # first occurrence -> write to jsonl
            out_obj = {
                "chunk_id": j.get("chunk_id"),
                "source_fragment": j.get("source_fragment"),
                "title": j.get("title"),
                "slug": j.get("slug"),
                "chunk_index": j.get("chunk_index"),
                "text": text,
                "source_file": j.get("source_file")
            }
            outf.write(json.dumps(out_obj, ensure_ascii=False) + "\n")
            seen[h] = {"hash": h, "file": str(path), "files": [str(path)]}
            unique += 1

    print("Done.")
    print("Total chunk files scanned:", total)
    print("Unique chunk texts kept:", unique)
    duplicates = total - unique
    print("Exact-duplicate chunk files skipped:", duplicates)
    # show a few duplicate examples
    dup_examples = [v for v in seen.values() if len(v["files"])>1]
    print("Duplicate groups found (examples):", min(5, len(dup_examples)))
    for ex in dup_examples[:5]:
        print(" - representative file:", ex["file"])
        print("   total duplicates for this text:", len(ex["files"]))
    print("\nWrote deduped JSONL to:", OUT_JSONL)
    if BACKUP.exists():
        print("Backup of previous deduped JSONL is at:", BACKUP)

if __name__ == "__main__":
    main()
