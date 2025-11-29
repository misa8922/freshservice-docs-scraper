# src/scraper/chunk_texts.py
#4
"""
Chunk parsed docs (scraped or deduped) into word-based chunks for embedding/indexing.

Outputs:
 - data/clean/chunks/<slug>__<fragment>__chunk<N>.json  (one file per chunk)
 - data/clean/deduped_chunks.jsonl  (combined JSONL of all chunks)
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Input preference: prefer deduped_docs.jsonl, otherwise use scraped_fragments.jsonl
PREFERRED = Path("data/clean/deduped_docs.jsonl")
FALLBACK = Path("data/clean/scraped_fragments.jsonl")
INPUT_FILE = PREFERRED if PREFERRED.exists() else FALLBACK

if not INPUT_FILE.exists():
    print("ERROR: No input file found. Tried:")
    print(" -", PREFERRED)
    print(" -", FALLBACK)
    sys.exit(1)

print("Using input for chunking:", INPUT_FILE)

OUT_DIR = Path("data/clean/chunks")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSONL = Path("data/clean/deduped_chunks.jsonl")

# chunk size in words and overlap (tweak these if needed)
CHUNK_WORDS = 300
OVERLAP_WORDS = 50

def normalize_whitespace(text: str) -> str:
    """Normalize whitespace and line endings, collapse excessive whitespace."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # collapse multiple newlines to two newlines max (preserve paragraph breaks)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # collapse multiple whitespace to single space
    text = re.sub(r"[ \t]{2,}", " ", text)
    # trim leading/trailing whitespace
    return text.strip()

def words_from_text(text: str) -> List[str]:
    """Split normalized text into words (keeps punctuation attached)."""
    text = normalize_whitespace(text)
    if not text:
        return []
    words = re.split(r"\s+", text)
    return [w for w in words if w]

def chunk_words(words: List[str], chunk_size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> List[Tuple[int,int,str]]:
    """
    Return list of tuples (start_index, end_index, chunk_text).
    end_index is exclusive (like Python slices).
    """
    if not words:
        return []
    chunks = []
    N = len(words)
    start = 0
    while start < N:
        end = min(start + chunk_size, N)
        chunk = words[start:end]
        chunks.append((start, end, " ".join(chunk)))
        if end >= N:
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks

def safe_slug(text: str, fallback: str = "doc") -> str:
    s = (text or fallback).lower()[:120]
    s = re.sub(r"[^\w\-_.]", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")

def clear_previous_outputs():
    # remove combined jsonl if exists
    try:
        if OUT_JSONL.exists():
            OUT_JSONL.unlink()
    except Exception as e:
        print("Warning: could not remove old JSONL:", e)

    # remove per-chunk files
    if OUT_DIR.exists():
        for f in OUT_DIR.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass

def main():
    clear_previous_outputs()

    total_chunks = 0
    per_doc_counts = []
    processed = 0

    with INPUT_FILE.open("r", encoding="utf-8") as inf, OUT_JSONL.open("w", encoding="utf-8") as outf:
        for line in inf:
            processed += 1
            try:
                rec = json.loads(line)
            except Exception:
                # skip malformed lines
                continue

            # fragment id / fragment name
            fragment = rec.get("fragment") or rec.get("fragment_id") or "unknown_fragment"
            title = rec.get("title") or rec.get("slug") or ""
            slug = safe_slug(title or fragment)

            # robust text extraction: prefer inner_text or full_text or full_text normalized form
            text = rec.get("inner_text") or rec.get("full_text") or rec.get("full_text_normalized") or ""
            text = normalize_whitespace(text)
            words = words_from_text(text)
            chunks = chunk_words(words)

            per_doc_counts.append((fragment, len(chunks)))

            for i, (start, end, chunk_text) in enumerate(chunks, start=1):
                chunk_id = f"{slug}__{fragment}__chunk{i}"
                out_obj = {
                    "chunk_id": chunk_id,
                    "source_fragment": fragment,
                    "title": title,
                    "slug": slug,
                    "chunk_index": i,
                    "chunk_word_start": int(start),
                    "chunk_word_end": int(end),
                    "text": chunk_text,
                    "source_file": rec.get("source_file"),
                }
                # write per-chunk file
                fname = OUT_DIR / f"{chunk_id}.json"
                try:
                    with fname.open("w", encoding="utf-8") as fh:
                        json.dump(out_obj, fh, ensure_ascii=False, indent=2)
                except Exception as e:
                    print("Warning: failed to write chunk file", fname, ":", e)
                    continue

                # append to combined JSONL
                try:
                    outf.write(json.dumps(out_obj, ensure_ascii=False) + "\n")
                except Exception as e:
                    print("Warning: failed to write to combined JSONL:", e)
                    # continue, don't stop
                total_chunks += 1

            # progress print every 50 processed fragments
            if processed % 50 == 0:
                print(f"[{processed}] processed fragments, total chunks so far: {total_chunks}")

    # summary
    per_doc_counts.sort(key=lambda x: x[1], reverse=True)
    print("Chunking complete.")
    print("Input file:", INPUT_FILE)
    print("Total fragments processed:", processed)
    print("Total chunks created:", total_chunks)
    print("Top 10 fragments by chunk count:")
    for frag, count in per_doc_counts[:10]:
        print(f" - {frag} : {count} chunks")

if __name__ == "__main__":
    main()
