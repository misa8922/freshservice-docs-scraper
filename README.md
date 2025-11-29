# Freshservice Docs — API Assistant

A compact Retrieval-Augmented Generation (RAG) assistant for Freshservice API docs.

**What it does**
- Scrapes Freshservice API docs into fragments.
- Parses & normalizes fragments, chunks text, and deduplicates chunks.
- Builds embeddings and a FAISS index for fast retrieval (local).
- Uses a remote LLM (OpenAI) to generate concise answers using retrieved doc snippets.
- Minimal HTML UI + FastAPI backend to ask questions and view citations.

---

## Quick links
- Code: `src/`  
  - `src/scraper/` — scraping/parsing/chunking/dedupe  
  - `src/embeddings/` — embedding + FAISS index build and local query  
  - `src/rag/` — RAG prompt + OpenAI call wrapper  
  - `src/server/` — FastAPI server that the UI talks to  
  - `src/ui/index.html` — minimal static UI
- Data (generated): `data/` — **ignored** from Git 


---


## Mermaid 

```mermaid

flowchart TD
  A["Freshservice UI / Docs"] --> B["data/raw/*.html"]
  B --> C["parse & normalize → deduped_docs.jsonl"]
  C --> D["chunk_texts → chunks/*.json"]
  D --> E["dedupe chunks → deduped_chunks.jsonl"]
  E --> F["embed → FAISS index + meta.jsonl"]
  F --> G["retrieve (top_k)"]
  G --> H["build prompt"]
  H --> I["OpenAI / LLM"]
  I --> J["Answer + citations"]


