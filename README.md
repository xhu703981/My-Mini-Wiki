# My-Mini-Wiki

A personal knowledge base. Drop in PDFs, notes, images, and code; Gemini compiles them into linked wiki articles; then you ask questions over the wiki through a hybrid-search RAG API.

## How it works

```
raw/ (PDF, text, images, code)
   │  compile_wiki.py   Gemini 2.5 Flash writes cross-linked Markdown articles;
   │                    processed.json tracks done files, so re-runs are incremental
   ▼
wiki/*.md
   │  lint.py           Gemini merges duplicate articles and fixes broken links
   │  build_index.py    chunk (6,000 chars, 300 overlap) + embed (gemini-embedding-001, 3072-d)
   ▼
OpenSearch index (HNSW vector field via Faiss, m=16 + BM25 text field)
   │  query_wiki.py     dense top-k + BM25 top-k, fused with Reciprocal Rank Fusion (k=60)
   ▼
api.py  →  FastAPI  POST /query  +  web UI at /
```

## Evaluation

`generate_eval_dataset.py` builds a 45-question test set (3 Q&A pairs from each of 15 articles). `evaluate_wiki.py` scores the full RAG pipeline with **RAGAS** on four metrics: faithfulness, answer relevancy, context precision, and context recall. Gemini 2.5 Pro is the judge.

## Setup

Create `.env`:

```
GEMINI_API_KEY=...
OPENSEARCH_ENDPOINT=https://...
OPENSEARCH_USER=...
OPENSEARCH_PASSWORD=...
```

Then:

```bash
pip install -r requirements.txt
python scripts/compile_wiki.py     # raw/ -> wiki/
python scripts/build_index.py      # wiki/ -> OpenSearch
python scripts/query_wiki.py       # ask from the terminal
python scripts/evaluate_wiki.py    # RAGAS report -> output/ragas_results.json
```

## Run with Docker

```bash
docker compose up --build          # http://localhost:8000
```

The image runs as a non-root user.

## Stack

Python, FastAPI, OpenSearch, Gemini API, RAGAS, Docker
