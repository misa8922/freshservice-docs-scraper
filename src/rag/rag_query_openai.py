# src/rag/rag_query_openai.py
#8
"""
RAG query runner: local retrieval + remote LLM (HTTP).
Drop-in script to query your local FAISS index and ask the remote OpenAI model
to produce concise answers (e.g., curl commands).

Usage:
  - Ensure .env has OPENAI_API_KEY and RAG_OPENAI_MODEL (e.g. gpt-4.1-mini).
  - Build local index first (faiss.index + meta.jsonl).
  - Run: python -m src.rag.rag_query_openai
"""
import os
import json
import textwrap
from pathlib import Path
from dotenv import load_dotenv
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import re
import sys

load_dotenv()

# --- Config & paths ---
FAISS_PATH = Path("data/index/faiss.index")
META_PATH = Path("data/index/meta.jsonl")

EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
TOP_K = int(os.getenv("RAG_TOP_K", "1"))           # single chunk for concise answers
MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "1500"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_CHAT_MODEL = os.getenv("RAG_OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")

# Safety defaults (do not lower temperature below 1 for gpt-5-nano — that model requires temperature 1)
DEFAULT_TEMPERATURE = float(os.getenv("RAG_TEMPERATURE", "1"))
MAX_COMPLETION_TOKENS = int(os.getenv("RAG_MAX_COMPLETION_TOKENS", "500"))

# Debugging: set RAG_DEBUG_RAW=1 in env to print raw assistant content (temporary)
DEBUG_RAW = os.getenv("RAG_DEBUG_RAW", "0") == "1"

# --- Helpers ---
def load_meta(meta_path: Path):
    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {meta_path}")
    metas = []
    with open(meta_path, "r", encoding="utf-8") as fh:
        for line in fh:
            metas.append(json.loads(line))
    return metas

def retrieve(query: str, top_k: int = TOP_K):
    if not FAISS_PATH.exists() or not META_PATH.exists():
        raise FileNotFoundError("FAISS index or meta.jsonl not found. Run local index builder first.")
    index = faiss.read_index(str(FAISS_PATH))
    metas = load_meta(META_PATH)
    model = SentenceTransformer(EMBED_MODEL)
    q_emb = model.encode([query], convert_to_numpy=True)
    # normalize (embedding pipeline earlier normalized as float32)
    q_emb = q_emb / np.linalg.norm(q_emb, axis=1, keepdims=True)
    q_emb = q_emb.astype("float32")
    D, I = index.search(q_emb, top_k)
    ids = I[0].tolist()
    scores = D[0].tolist()
    results = []
    for idx, sc in zip(ids, scores):
        if idx < 0 or idx >= len(metas):
            continue
        m = metas[idx]
        results.append({
            "score": float(sc),
            "chunk_id": m.get("chunk_id"),
            "title": m.get("title"),
            "source_fragment": m.get("source_fragment"),
            "source_file": m.get("source_file"),
            "text": m.get("text") or m.get("text_preview") or ""
        })
    return results

def build_prompt(question: str, retrieved: list):
    # Build a short context with citations
    context_blocks = []
    for i, r in enumerate(retrieved, start=1):
        txt = r.get("text", "").strip()
        if len(txt) > MAX_CONTEXT_CHARS:
            txt = txt[:MAX_CONTEXT_CHARS] + " ... (truncated)"
        context_blocks.append(f"[{i}] {r.get('chunk_id')} - {r.get('title')}\n{txt}")
    context = "\n\n".join(context_blocks) if context_blocks else ""
    system_prompt = (
        "You are an assistant that answers user questions using only the provided documentation snippets when the "
        "answer exists there. If the answer is not present in the snippets, say you don't know and suggest where to look. "
        "Be concise. When returning an executable shell command, always start with exactly one short sentence (no more than "
        "12 words) that describes the command, e.g. 'This is your curl command to create a ticket.' Then provide the command "
        "inside a triple-backtick bash code block."
    )
    # Instruct the assistant to return code blocks only when the answer is an executable command.
    user_prompt = (
        f"Question: {question}\n\n"
        f"Documentation snippets:\n{context}\n\n"
        "Answer concisely. If the user asked for a shell command (curl, etc.), begin with a single descriptive sentence, "
        "then return the command inside a triple-backtick code block (```bash ... ```). Otherwise, return a short textual "
        "answer and include citation numbers at the end like [1]."
    )
    return system_prompt, user_prompt

def call_openai_chat(system_prompt: str, user_prompt: str,
                     model: str = OPENAI_CHAT_MODEL,
                     max_completion_tokens: int = MAX_COMPLETION_TOKENS,
                     temperature: float = DEFAULT_TEMPERATURE):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set. Put it in your .env or environment to enable remote LLM.")
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        # new parameter names used by recent OpenAI models
        "max_completion_tokens": max_completion_tokens,
        "temperature": temperature
    }
    # Helpful debug preview (avoid printing huge context)
    try:
        preview = {
            "model": model,
            "messages_lengths": [len(system_prompt), len(user_prompt)],
            "total_message_chars": len(system_prompt) + len(user_prompt)
        }
        print("Calling OpenAI with payload preview:", json.dumps(preview))
    except Exception:
        print("Calling OpenAI (payload preview unavailable).")
    resp = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        # Print verbose error JSON (helps debugging unsupported params / model issues)
        try:
            j = resp.json()
            print("OpenAI returned status", resp.status_code)
            print("Full error JSON from OpenAI:\n", json.dumps(j, indent=2))
        except Exception:
            print("OpenAI returned status", resp.status_code, "and non-JSON response:", resp.text)
        resp.raise_for_status()
    return resp.json()

def extract_preface_and_code(text: str):
    """
    Returns a tuple (preface, code).
    - preface: text immediately before the first fenced code block (stripped), or None if none.
    - code: content of the first fenced code block OR a single-line command fallback, or None if nothing.
    """
    if not text:
        return None, None

    # Try to find preface + first fenced code block
    m = re.search(
        r"(?s)^(?P<preface>.*?)(?:\r?\n)?```(?:bash|sh|shell)?\s*(?P<code>[\s\S]*?)\s*```",
        text, re.IGNORECASE
    )
    if m:
        preface = m.group("preface").strip()
        code = m.group("code").strip()
        if not preface:
            preface = None
        return preface, code

    # No fenced code block: try to find a single-line command in the first few lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None, None

    # Heuristic: check the first 3 lines for a command start
    for ln in lines[:3]:
        if ln.startswith("curl") or ln.startswith("http") or ln.startswith("wget") or ln.startswith("sudo") or ln.startswith("ssh"):
            return None, ln

    # Last resort: return the entire content as preface (no code)
    return text.strip(), None

def redact_possible_secrets_from_code(code: str):
    """
    Simple heuristic redaction to avoid printing basic secrets in -u user:KEY patterns.
    Keeps the line readable but replaces token-like values.
    """
    if not code:
        return code
    # redact -u user:SECRET or -u user:SECRET@... patterns
    code = re.sub(r"(-u\s+[^:\s]+):\S+", r"\1:***REDACTED***", code)
    # redact Authorization headers in -H "Authorization: Bearer SECRET"
    code = re.sub(r'(Authorization:\s*Bearer\s+)(\S+)', r'\1***REDACTED***', code, flags=re.IGNORECASE)
    return code

# --- CLI main loop ---
def main():
    print("RAG query runner (local retrieval + remote LLM).")
    print(f"Local index: {FAISS_PATH}")
    print(f"Meta: {META_PATH}")
    print(f"Local embedding model: {EMBED_MODEL}")
    print(f"Remote LLM model: {OPENAI_CHAT_MODEL} (requires OPENAI_API_KEY)")

    # quick pre-check
    if not FAISS_PATH.exists() or not META_PATH.exists():
        print("FAISS index or meta.jsonl missing. Run index builder before querying.")
        sys.exit(1)

    while True:
        try:
            q = input("\nEnter question (or 'exit'): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            break

        try:
            retrieved = retrieve(q, top_k=TOP_K)
        except Exception as e:
            print("Retrieval error:", e)
            continue

        if not retrieved:
            print("No relevant chunks found.")
            continue

        print("\nRetrieved context (top_k):")
        for i, r in enumerate(retrieved, start=1):
            print(f"[{i}] chunk={r['chunk_id']} score={r['score']:.4f} source={r.get('source_file')}")
            print("    preview:", textwrap.shorten(r.get("text","").replace("\n"," "), width=240))

        if not OPENAI_API_KEY:
            print("\nNote: OPENAI_API_KEY not set — remote LLM disabled. Set it in .env to enable answer generation.")
            continue

        system_prompt, user_prompt = build_prompt(q, retrieved)
        try:
            raw = call_openai_chat(system_prompt, user_prompt)
        except Exception as e:
            print("Error calling OpenAI API:", e)
            continue

        # debug: show keys & usage
        keys = list(raw.keys())
        print("\nOpenAI response object preview keys:", keys)
        # attempt to extract content robustly
        choices = raw.get("choices", [])
        if not choices:
            print("No choices returned by OpenAI. Full response:")
            print(json.dumps(raw, indent=2))
            continue

        # typical structure: choices[0]['message']['content']
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message", {}) or {}
        content = message.get("content", "") or ""

        # Optional debug: print raw assistant content (controlled by env var)
        if DEBUG_RAW:
            print("\n--- RAW ASSISTANT CONTENT (debug) ---")
            print(content)
            print("--- END RAW ASSISTANT CONTENT ---\n")

        if not content:
            # some responses embed in 'text' or other fields — fallback prints for debugging
            print("\n=== LLM Answer ===\n(no textual answer extracted)")
            print("Choices JSON (for debugging):")
            print(json.dumps(choices, indent=2))
        else:
            # Extract preface + code (or fallback)
            preface, code = extract_preface_and_code(content)

            # Prefer printing: preface (if present) then fenced code block (if present), else raw content
            if preface:
                print("\n=== LLM Answer (preface) ===\n")
                print(preface)

            if code:
                # redact obvious secrets before printing
                safe_code = redact_possible_secrets_from_code(code)
                print("\n```bash")
                print(safe_code)
                print("```")
            else:
                # No code: print raw content if preface wasn't already the full content
                if not preface:
                    print("\n=== LLM Answer ===\n")
                    print(content.strip())

        # extra debug info
        print("\n=== Debug info ===")
        print("finish_reason:", finish_reason)
        usage = raw.get("usage")
        if usage:
            print("usage:", json.dumps(usage))
        else:
            print("usage: (not present)")

if __name__ == "__main__":
    main()
