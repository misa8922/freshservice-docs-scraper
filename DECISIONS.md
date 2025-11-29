# Project Decisions Log

### Environment
- Working environment: VS Code (local machine)
- Python Version: 3.12.2
- Git initialized: Yes

### Scraping Strategy
- Page Type: DYNAMIC
-Tool: Playwright

### Notes
- Folder structure created

### phase 1
-scraping using hash nav tech
-parsing
-chunking
-deduping chunks

### phase 2
-local embeddings using model local SentenceTransformer model(all-MiniLM-L6-v2)
-creating faiss index local
-testing local retrieval 

### RAG
-generating responses using remote llm
-Openai Api
-model gpt-4.1-mini

### phase 3
-built an endpoint using FASTApi 
-uvicorn
-front end a simple html ui


