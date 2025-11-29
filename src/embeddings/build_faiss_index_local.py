# src/embeddings/build_faiss_index_local.py
#6
"""
Build a FAISS index using a local SentenceTransformer model.

Input:
 - data/clean/deduped_chunks.jsonl  (one JSON line per chunk, keys: chunk_id, text, ...)

Outputs:
 - data/index/faiss.index
 - data/index/meta.jsonl  
"""
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
import math
from tqdm import tqdm

# Files
INPUT = Path("data/clean/deduped_chunks.jsonl")
OUT_DIR = Path("data/index")
OUT_DIR.mkdir(parents=True, exist_ok=True)
FAISS_PATH = OUT_DIR / "faiss.index"
META_PATH = OUT_DIR / "meta.jsonl"

# Model & batching
MODEL_NAME = "all-MiniLM-L6-v2"  # small, fast, 384-dim
BATCH_SIZE = 64

def load_records(input_path):
    recs = []
    with open(input_path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            recs.append(rec)
    return recs

def build_index(records, model_name=MODEL_NAME, batch_size=BATCH_SIZE):
    model = SentenceTransformer(model_name)
    dim = model.get_sentence_embedding_dimension()
    # We'll use inner-product on L2-normalized vectors -> cosine similarity
    index = faiss.IndexFlatIP(dim)

    metas = []
    vectors = []

    # encode in batches
    n = len(records)
    n_batches = math.ceil(n / batch_size)
    for i in tqdm(range(n_batches), desc="Embedding batches"):
        start = i * batch_size
        end = min((i + 1) * batch_size, n)
        texts = [records[j]["text"] for j in range(start, end)]
        embs = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        # normalize rows
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embs = embs / norms
        vectors.append(embs.astype("float32"))
        for j in range(start, end):
            metas.append({
                "chunk_id": records[j].get("chunk_id"),
                "source_fragment": records[j].get("source_fragment"),
                "title": records[j].get("title"),
                "slug": records[j].get("slug"),
                "chunk_index": records[j].get("chunk_index"),
                "source_file": records[j].get("source_file"),
                "text_preview": (records[j].get("text") or "")[:400]
            })

    if vectors:
        all_vecs = np.vstack(vectors).astype("float32")
        index.add(all_vecs)
    else:
        all_vecs = np.zeros((0, dim), dtype="float32")

    return index, metas, dim

def save_index(index, faiss_path, meta_records, meta_path):
    faiss.write_index(index, str(faiss_path))
    with open(meta_path, "w", encoding="utf-8") as fh:
        for m in meta_records:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")

def main():
    if not INPUT.exists():
        print("Input not found:", INPUT)
        return
    records = load_records(INPUT)
    print("Total chunks to embed:", len(records))
    if len(records) == 0:
        print("No chunks found. Exiting.")
        return

    index, metas, dim = build_index(records)
    print("Index built. vec count:", index.ntotal, "dim:", dim)

    save_index(index, FAISS_PATH, metas, META_PATH)
    print("FAISS index saved to:", FAISS_PATH)
    print("Metadata saved to:", META_PATH)

if __name__ == "__main__":
    main()
