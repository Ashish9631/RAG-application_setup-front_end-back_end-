# Document Copilot — implementation checklist

Work top to bottom. Each phase unlocks the next. Check items off as you go.

## Where to start (backend vs frontend?)

**Start with infrastructure, then backend-first on the data/AI spine, then frontend in parallel once auth exists.**

| Layer | Why this order |
| ----- | -------------- |
| Supabase + tools | Everything depends on Postgres, Auth, and env config |
| Backend schema + ingestion | The product is grounded answers from a corpus — no corpus, no product |
| Auth (both sides) | First real vertical slice needs a logged-in user |
| Chat plumbing (stub → real) | Proves streaming end-to-end before you wire retrieval |
| Retrieval + LLM | Core intelligence lives in the backend |
| Frontend polish | Citations UI only matters once the backend returns real citations |
| Deploy + pilot | Client brief definition of done is analyst time saved |

You can scaffold the frontend SPA early (Phase 4), but don't sink time into citation UI until Phase 10. The critical path is: **schema → ingest → retrieve → generate → cite**.

---

## Phase 0 — Prerequisites & accounts

- [ ] Install Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io/)
- [ ] Create a [Supabase](https://supabase.com) project → follow [guides/supabase-setup.md](guides/supabase-setup.md)
- [ ] Save credentials: project URL, anon key, service_role key, direct `DATABASE_URL`
- [ ] Create an [OpenAI API key](https://platform.openai.com/api-keys) (needed from Phase 8 onward)
- [ ] Copy `backend/.env.example` → `backend/.env` and fill in Supabase + DB values
- [ ] Copy `frontend/.env.example` → `frontend/.env` and fill in Supabase + API URL

---

## Phase 1 — Sample corpus (independent, do early)

- [ ] Edit `USER_AGENT` in `data/download.py` (SEC requires a real contact string)
- [ ] Run `uv run data/download.py` from repo root
- [ ] Confirm 10-K filings for AAPL, MSFT, NVDA, AMZN, GOOGL (2021–2025) land under `data/downloads/`
- [ ] Spot-check `manifest.json` — you'll use this as the ingestion input list

---

## Phase 2 — Backend scaffold

- [ ] `cd backend && uv sync` — add deps per [guides/backend-setup.md](guides/backend-setup.md)
- [ ] Create `app/main.py` — FastAPI app, CORS from `ALLOWED_ORIGINS`, health route
- [ ] Create `app/config.py` — pydantic-settings; fail fast on missing env vars
- [ ] Confirm `uv run uvicorn app.main:app --reload` serves `GET /health`

---

## Phase 3 — Database schema (Alembic + SQLAlchemy)

- [ ] `uv run alembic init alembic` — wire `env.py` to `app.config.settings.DATABASE_URL` and model metadata
- [ ] Define SQLAlchemy models in `app/database/models.py`:
  - [ ] `profiles`
  - [ ] `chat_threads`, `chat_messages`, `message_citations`
  - [ ] `source_documents`, `document_chunks` (embedding + `tsvector` columns)
- [ ] Generate migration: `uv run alembic revision --autogenerate -m "initial schema"`
- [ ] Review migration — add explicit ops Alembic can't infer:
  - [ ] `create extension if not exists vector`
  - [ ] `vector(1536)` embedding column
  - [ ] generated `tsvector` column on chunks
  - [ ] HNSW index (vectors), GIN indexes (full-text + JSON metadata)
  - [ ] RLS enablement + policies (user owns their chats)
- [ ] `uv run alembic upgrade head` against your Supabase project
- [ ] Add `app/database/supabase.py` — user-scoped and service-role clients

---

## Phase 4 — Frontend scaffold + auth

- [ ] Scaffold Vite + React + TS per [guides/frontend-setup.md](guides/frontend-setup.md)
- [ ] Add Tailwind, shadcn/ui, React Router
- [ ] Create `src/lib/env.ts`, `src/lib/supabase.ts`, `src/lib/http.ts`, `src/lib/api.ts`
- [ ] Build login / sign-up pages (Supabase email auth only)
- [ ] Protect chat routes — redirect unauthenticated users to login
- [ ] Backend: `app/auth/dependencies.py` — verify `Authorization: Bearer <token>` via Supabase
- [ ] Smoke test: sign in in the browser, hit a protected backend route with the token

---

## Phase 5 — Chat plumbing (stubbed assistant)

Prove the full request path before RAG. The analyst should see a streaming reply; content can be fake for now.

- [ ] Backend: `app/api/chat.py` — thread CRUD (list, create, load messages)
- [ ] Backend: `POST /chat/stream` — accepts AI SDK message format, returns stub streamed text
- [ ] Backend: `app/chat/streaming.py` — emit AI SDK-compatible stream events
- [ ] Frontend: chat page with Vercel AI SDK `useChat` pointed at FastAPI (not a Next route)
- [ ] Frontend: thread sidebar — create thread, switch threads, load history via `api.ts`
- [ ] Smoke test: log in → new thread → send message → see streamed stub response → refresh → history persists

---

## Phase 6 — Ingestion pipeline

Turn downloaded SEC filings into searchable chunks in Supabase.

- [ ] Build `backend/ingest/` — parse HTML/Markdown from downloaded filings
- [ ] Normalize to Markdown; write `source_documents` rows (ticker, company, filing type, year, accession, source URL)
- [ ] Chunk with metadata: page/section, chunk index, token count, ticker, year
- [ ] Embed chunks with OpenAI (`text-embedding-3-small`, 1536 dims)
- [ ] Populate `document_chunks` — text, embedding, generated `tsvector`
- [ ] Run ingestion against the full sample corpus (25 filings)
- [ ] Spot-check: query a few chunks in Supabase dashboard — text and metadata look right

---

## Phase 7 — Retrieval (hybrid search)

- [ ] `app/retrieval/queries.py` — pgvector semantic search over `document_chunks.embedding`
- [ ] `app/retrieval/queries.py` — Postgres full-text search over `document_chunks.search_vector`
- [ ] `app/retrieval/fusion.py` — Reciprocal Rank Fusion in Python
- [ ] `app/retrieval/retriever.py` — query → ranked source passages (+ optional neighbor chunks)
- [ ] Unit tests for fusion and retriever (mock DB boundary)
- [ ] Manual test: run a retrieval query for a known fact in a filing — correct chunk in top results

---

## Phase 8 — LLM orchestration (PydanticAI)

- [ ] `app/assistant/deps.py`, `outputs.py` — `GroundedAnswer`, `Citation`, `SourcePassage`
- [ ] `app/assistant/agent.py` — PydanticAI agent with retrieval tools (`search_filings`, `read_chunk`, etc.)
- [ ] `app/assistant/instructions.md` — product contract from client brief:
  - [ ] answer only from retrieved passages
  - [ ] cite every factual claim
  - [ ] refuse when corpus lacks evidence
  - [ ] no stock picks or investment advice
- [ ] `app/chat/orchestrator.py` — one turn: retrieve → agent → stream → persist
- [ ] Wire real assistant into `POST /chat/stream` (replace stub)
- [ ] Persist user message, assistant message, and citation records after successful run

---

## Phase 9 — Grounding & trust enforcement

This is the client brief's non-negotiable contract.

- [ ] `app/grounding/validator.py` — every citation maps to a retrieved passage
- [ ] Reject answers that cite chunks not in the retrieval set
- [ ] Return controlled failure (not a polished hallucination) when validation fails
- [ ] Unit tests for citation extraction and grounding enforcement
- [ ] Manual test: ask something **not** in the corpus — bot says it doesn't know (no invented facts)

---

## Phase 10 — Frontend: citations & trust UI

- [ ] Render inline citations on assistant messages (filing, page/section, company)
- [ ] Source passage panel — click citation → see underlying excerpt
- [ ] Empty states (no threads, no messages)
- [ ] Error states (auth expired, network/CORS, retrieval failure, grounding failure)
- [ ] Streaming status indicator while assistant is generating

---

## Phase 11 — Pilot-quality validation

Run the 10 example questions from [client-brief.md](client-brief.md). For each:

- [ ] Answer is grounded in the corpus (not hallucinated)
- [ ] Every factual claim has a citation
- [ ] Cited passage is verifiable in one click
- [ ] Cross-year / cross-company comparisons work where filings support them
- [ ] Question 10 (generative AI margins): bot refuses to infer beyond what filings say

Fix retrieval gaps or prompt issues until the pilot group would trust this for intake work.

---

## Phase 12 — Deploy (Railway)

- [ ] Backend service on Railway — Uvicorn, env vars from `backend/.env`
- [ ] Frontend service on Railway — Vite build, `VITE_*` vars baked at build time
- [ ] Update `ALLOWED_ORIGINS` to production frontend URL
- [ ] Re-run `alembic upgrade head` against production Supabase (if separate project)
- [ ] End-to-end smoke test on deployed URLs

---

## Phase 13 — Definition of done (client brief)

- [ ] 5 senior analysts use it for one week
- [ ] Each reports ≥ 3 hours saved per week on source-document intake
- [ ] No incidents of confident wrong answers (hallucinations)
- [ ] Rollout decision: firm-wide or iterate

---

## Quick reference

| Doc | Purpose |
| --- | ------- |
| [client-brief.md](client-brief.md) | Who Driftwood is, what "trust" means, example questions, definition of done |
| [architecture.md](architecture.md) | System design, data model, streaming contract, module layout |
| [guides/supabase-setup.md](guides/supabase-setup.md) | Supabase project + credentials |
| [guides/backend-setup.md](guides/backend-setup.md) | Backend init, Alembic, run commands |
| [guides/frontend-setup.md](guides/frontend-setup.md) | Frontend init, run commands |
