#9

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn




# import existing rag functions
from src.rag.rag_query_openai import retrieve, build_prompt, call_openai_chat, TOP_K

app = FastAPI()


# allow cross-origin requests from frontend
from fastapi.middleware.cors import CORSMiddleware

# If you are developing locally and just want it to work:
origins = [
       
    "http://0.0.0.0:8001",
    "http://localhost:8001",
    "*",  
]                     

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,    
    allow_credentials=True,
    allow_methods=["*"],      # allow POST, OPTIONS, GET, etc.
    allow_headers=["*"],      # allow Content-Type, Authorization, etc.
)

class QueryRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_question(req: QueryRequest):
    q = req.question.strip()

    # 1. retrieve from local index
    retrieved = retrieve(q, top_k=TOP_K)

    # prepare retrieval info for UI (scores, chunk ids)
    retrieved_info = [
        {
            "chunk_id": r["chunk_id"],
            "score": r["score"],
            "title": r["title"],
            "preview": r["text"][:200]
        }
        for r in retrieved
    ]

    # 2. build prompt for LLM
    system, user_prompt = build_prompt(q, retrieved)


    # 3. remote LLM call
    llm_raw = call_openai_chat(system, user_prompt)

    # extract assistant text
    answer = llm_raw["choices"][0]["message"]["content"].strip()

    return {
    "question": q,
    "answer": answer,
    "retrieved": retrieved_info
     }
    

    


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
