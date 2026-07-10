# AI Q&A Backend — Design & Architecture

The zread-ai backend is a self-hosted RAG (Retrieval-Augmented Generation)
service that indexes a GitHub repository's documentation into vector
embeddings and answers questions about it via an OpenAI-compatible LLM.

It is the "AI brain" missing from the fork's GitHub-only data layer. The fork
client connects to it with a single env var (`ZREAD_AI_BACKEND_URL`); when
unset, all existing tools behave exactly as before (graceful degradation).

## Architecture

```
┌──────────────────────────┐         ┌─────────────────────────────────┐
│  zread fork (client)     │         │  backend/ (FastAPI service)     │
│  - existing MCP tools    │  HTTPS  │                                 │
│  - ai_client.py ─────────┼────────►│  POST /api/v1/repos/.../index   │
│  - ask / chat MCP tools  │  SSE    │  GET  /api/v1/repos/.../status  │
│  - `zread ai` command    │◄────────┤  POST /api/v1/talk              │
└──────────┬───────────────┘         │  POST /api/v1/talk/{id}/message │
           │ reads from GitHub       │  DEL  /api/v1/talk/{id}         │
           ▼                         │  GET  /healthz                  │
     api.github.com / raw            └──────┬──────────────┬────────────┘
     .githubusercontent.com                 │              │
                                  ┌────────▼──────┐ ┌──────▼─────────┐
                                  │ Indexer       │ │ RAG / LLM      │
                                  │ - fetch tree  │ │ - embed query   │
                                  │ - filter docs │ │ - top-kretrieve │
                                  │ - chunk       │ │ - build prompt  │
                                  │ - embed       │ │ - SSE stream    │
                                  │ - store       │ └──────┬──────────┘
                                  └──────┬────────┘        │
                                         ▼                 ▼
                                  ┌──────────────────────────────────┐
                                  │ SQLite + sqlite-vec (vectors)    │
                                  │ OpenAI-compatible LLM API         │
                                  └──────────────────────────────────┘
```

**Key principle:** the backend is self-contained — it has its own GitHub
fetcher (with its own `GITHUB_TOKEN`) and its own LLM config. The fork client
only needs `ZREAD_AI_BACKEND_URL` to reach it.

## Vector store: SQLite + sqlite-vec

A single SQLite file holds everything: repo metadata, text chunks, talk
sessions, and (via the `vec0` virtual table) the embedding vectors. No
external database server is required.

This is sufficient for tens of thousands of chunks per repo (a monorepo's
worth of docs). The KNN query uses sqlite-vec's native `MATCH` operator:

```sql
SELECT chunk_id, distance
FROM embeddings
WHERE embedding MATCH ? AND k = ?
ORDER BY distance ASC
```

The `embeddings` table is global across repos; repo isolation is enforced at
the join level (`WHERE c.repo_id = ?`). The inner query over-fetches
(`k * 4`) to compensate for cross-repo chunks being filtered out.

### When to move to pgvector

- **>100k chunks per repo** (you're indexing full source, not just docs)
- **Multi-team concurrency** causing write contention on the single SQLite file
- **Cross-repo semantic search** (a single query spans many repos)

At that point, swap `app/retriever.py` and `app/db.py` for a pgvector-backed
implementation. The indexer, embedder, and LLM layers are unchanged.

## Chunking strategy

Markdown files are split on ATX headers (`#`, `##`, …). Each chunk carries
a heading path like `"Installation > Docker"` so the LLM can cite sources.
Sections larger than `CHUNK_MAX_TOKENS` (default 800) are further split by
token windows with `CHUNK_OVERLAP_TOKENS` (default 100) overlap.

Each chunk's text is prefixed with a context anchor —
`[file_path § heading]` — so the embedding "knows" where the content came
from, improving retrieval quality.

Token counting uses `tiktoken`'s `cl100k_base` encoding (the same family
OpenAI's models use), which is a good proxy even for non-OpenAI providers.

## Re-index triggers

Indexing is **idempotent**: re-indexing the same `{owner}/{repo}@{ref}`
deletes old chunks/embeddings in a transaction before inserting fresh ones.
The idempotency key is the `repo_id` string (`owner/repo@ref`).

Re-indexing happens when:
1. A user explicitly calls `POST /api/v1/repos/{owner}/{name}/index`.
2. The first question on an un-indexed repo auto-triggers indexing inside
   the SSE stream (`ensure_indexed_with_progress` in the talk path). The
   HTTP response starts immediately and emits `event:status` progress
   events (`indexing` → `success`/`error`) while indexing runs, so the
   client is never blocked waiting for the index to finish. A per-repo lock
   ensures two concurrent first-questions on the same repo index it once.

If the talk is deleted mid-stream (e.g. the client timed out and cleaned up),
the stream emits a terminal `event:error {"text":"talk closed"}` instead of
crashing — the RAG layer raises `TalkGoneError`, which the router converts to
a clean SSE event.

**Out of scope:** automatic re-index on Git push (webhooks). For MVP, a manual
re-index call or the first-question flow is sufficient. A future enhancement
could poll the repo's `pushed_at` and re-index when it changes.

## Authentication (CWE-306 mitigation)

Every `/api/v1/*` route is gated by a FastAPI dependency (`app/auth.py`) that
requires a shared secret in the `Authorization: Bearer <key>` header. The
secret is configured via `BACKEND_API_KEY` (env) on the server and
`ZREAD_AI_API_KEY` on the client; they must match.

- **Constant-time comparison** (`hmac.compare_digest`) resists timing attacks.
- **`/healthz` is intentionally open** — it's the Docker healthcheck target
  and exposes no sensitive data (just `status`/`version`).
- **Fail-open with a warning when unset:** if `BACKEND_API_KEY` is empty, the
  API is left open (for local dev / first-run convenience), but a warning is
  logged at startup. Set the key before exposing the service on a network.

Without this, any caller who can reach the backend could trigger indexing and
spend the operator's GitHub API quota and LLM credits.


## LLM provider compatibility

The backend talks to any OpenAI-compatible `/chat/completions` and
`/embeddings` endpoint. Tested shapes:

| Provider | Base URL | Notes |
|----------|----------|-------|
| OpenAI | `https://api.openai.com/v1` | Default |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/deployments/<dep>` | Use deployment names as model |
| OpenRouter | `https://openrouter.ai/api/v1` | Model names like `openai/gpt-4o-mini` |
| Ollama (local) | `http://localhost:11434/v1` | Key field must be non-empty |
| LiteLLM (local) | `http://localhost:4000/v1` | Proxies any provider |

### Streaming delta normalization

The `stream_chat` function normalizes provider variance in the SSE delta:

- `delta.content` → `text` (standard OpenAI)
- `delta.reasoning_content` → `reasoning` (GLM/o1-style thinking)

These are forwarded into the client-facing SSE events so reasoning models
can surface their chain-of-thought. Empty deltas and malformed JSON lines
are tolerated without crashing the stream.

## SSE wire format

The client parser is tested byte-for-byte. The exact format:

```
event:answer
data:{"reasoning_content":"<optional thinking>","text":"<incremental text>"}

event:round_finish
data:{"reasoning_content":"","text":"<full answer text>"}

event:finish
data:{}
```

- `event:answer` → incremental token deltas (may carry `text`, `reasoning_content`, or both).
- `event:round_finish` → full concatenated answer, sent once.
- `event:finish` → terminates the client's reader.
- `event:error` with `{"text":...}` → client yields the error then stops.

At least one non-empty payload is always sent before `finish`.

## Running the tests

### Backend

```bash
cd backend
pip install -e ".[dev]"
pytest
```

### Fork client (includes the SSE parser tests)

```bash
uv run --extra dev pytest tests/test_ai_client.py tests/test_ai_config.py
```

## File map

```
backend/
├── pyproject.toml          # separate project: fastapi, sqlite-vec, openai, tiktoken
├── Dockerfile              # slim Python image, exposes 8709
├── .env.example            # all backend settings documented
├── app/
│   ├── main.py             # FastAPI app, CORS, router mounts, /healthz
│   ├── config.py           # pydantic-settings (env > .env > defaults)
│   ├── db.py               # SQLite + sqlite-vec schema + connection factory
│   ├── models.py           # Pydantic DTOs + response envelope
│   ├── github.py           # backend's own GitHub fetcher (tree + raw)
│   ├── chunker.py          # markdown → chunks (header split + token windows)
│   ├── embedder.py         # OpenAI-compatible embeddings (batched)
│   ├── indexer.py          # full pipeline: fetch → chunk → embed → store
│   ├── retriever.py        # vector KNN retrieval via sqlite-vec
│   ├── llm.py              # streaming chat + delta normalization
│   ├── rag.py              # orchestration: ensure_indexed_with_progress → retrieve → stream
│   └── routers/
│       ├── index.py        # POST .../index, GET .../status
│       └── talk.py         # POST /talk, POST /talk/{id}/message (SSE), DEL
└── tests/                  # 57 tests: chunker, retriever, talk, github, llm, retry
```
