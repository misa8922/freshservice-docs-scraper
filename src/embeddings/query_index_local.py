# src/embeddings/query_local_index.py
#7
"""
Interactive query against local FAISS index built by build_faiss_index_local.py
Usage example:
 python -m src.embeddings.query_local_index
"""
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

FAISS_PATH = Path("data/index/faiss.index")
META_PATH = Path("data/index/meta.jsonl")
MODEL_NAME = "all-MiniLM-L6-v2"

TOP_K = 3

def load_meta(meta_path):
    metas = []
    with open(meta_path, "r", encoding="utf-8") as fh:
        for line in fh:
            metas.append(json.loads(line))
    return metas

def main():
    if not FAISS_PATH.exists() or not META_PATH.exists():
        print("Index or meta not found. Please run the build script first.")
        return

    index = faiss.read_index(str(FAISS_PATH))
    metas = load_meta(META_PATH)
    model = SentenceTransformer(MODEL_NAME)

    print("Index loaded. Total vectors:", index.ntotal)
    while True:
        q = input("\nEnter query (or 'exit'): ").strip()
        if not q:
            continue
        if q.lower() in ("exit","quit"):
            break

        q_emb = model.encode([q], convert_to_numpy=True)
        # normalize
        q_emb = q_emb / np.linalg.norm(q_emb, axis=1, keepdims=True)
        q_emb = q_emb.astype("float32")

        D, I = index.search(q_emb, TOP_K)
        scores = D[0].tolist()
        ids = I[0].tolist()

        print(f"\nTop {TOP_K} results:")
        for rank, (idx, sc) in enumerate(zip(ids, scores), start=1):
            if idx < 0 or idx >= len(metas):
                continue
            m = metas[idx]
            print(f"\n[{rank}] score={sc:.4f} chunk={m.get('chunk_id')} title={m.get('title')}")
            preview = m.get("text_preview","").replace("\n"," ")[:400]
            print("    preview:", preview)

if __name__ == "__main__":
    main()
