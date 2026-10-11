# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working agreement (read first)

- **Backend (`app/`, `alembic/`, `tests/`, `pyproject.toml`, `docker-compose.yml`, `Dockerfile`) is READ-ONLY and suggestion-only.** Do not create or edit backend code. Instead, give proposals for improvement and next steps, and explain in detail *how* each part of the backend architecture works and *why* you recommend a decision (alternatives, trade-offs, what it protects against). Backend suggestions may include code snippets inside the chat reply, never written to files.
- **Frontend (`frontend/`) is writable.** Write code there freely.
- Docs (`CLAUDE.md`, `REPOMAP.md`, `docs/`) may be edited.
- Talk to the user in **Serbian**. API responses/errors and code comments stay in **English** (the exception is `NO_ANSWER_MESSAGE` / `NO_SOURCES_MESSAGE` in `chat/prompts.py`, which are user-facing Serbian text).
- The user is building this project to learn and for their CV: explain per file/module how it works and why (flow, design choices, trade-offs), not just what changed.
- `README.md` describes the original 7-phase plan (phase 0–7: foundations, auth/sessions, ingestion, retrieval/chat, cache, all LLM providers, quizzes, evaluation). It is partly stale (wrong file names in the tree, mentions `/health`-only endpoints and a worker container that `docker-compose.yml` does not define). Trust the code and `REPOMAP.md` over it.
- See `REPOMAP.md` for the file-level map, request flows and the backend improvement backlog.

## Commands

Backend (Python ≥3.14, venv in `./venv`; torch must be installed separately as the CPU build, otherwise pip pulls the CUDA build):

```bash
source venv/bin/activate
pip install -e ".[dev]"

docker compose up -d db redis                 # Postgres 17 + pgvector, Redis 7
alembic upgrade head                          # migrations 0001–0006
uvicorn app.main:app --reload                 # API on :8000, Swagger on /docs (needs JWT_SECRET >= 32 chars in .env)
celery -A app.worker worker --loglevel=info   # ingestion worker (docker-compose has NO worker service)

ruff check . && ruff format --check .
mypy app
lint-imports                                  # module boundary contracts in .importlinter
```

Tests (need Postgres and Redis reachable at the `.env` URLs; they create/use database `rag_test` and Redis db 15, and drop+recreate all tables each session):

```bash
pytest                                        # excludes -m slow and -m live by default
pytest tests/test_chat.py::test_name          # single test
pytest -m slow                                # real embedding model (downloads from the internet)
pytest -m live                                # real Gemini call using the key from .env
```

Frontend (`frontend/`, Vite + React 19 + TypeScript, no test runner):

```bash
cd frontend && npm install
npm run dev        # Vite proxies /api -> VITE_API_TARGET (default http://localhost:8000); no CORS needed in dev
npm run build      # tsc -b && vite build
npm run lint       # oxlint
```

## Backend architecture (big picture)

Modular monolith under `app/modules/`, strictly layered. Each module exposes a public interface only through its `__init__.py` (re-exports of `router`, service functions, schemas); **other modules may import only that**, never `module.service`/`models`/`repository`. `.importlinter` enforces this (run `lint-imports` before proposing structural changes). Dependency direction, bottom to top:

`shared` → `auth`, `jobs`, `embeddings` (leaves) → `sessions` (auth only) → `llm` (self-contained) → `sources` → `retrieval` (sources + embeddings) → `cache` (retrieval + sessions) → `chat` (retrieval + cache + llm + embeddings + sessions).

Key cross-file mechanics that are not obvious from one file:

- **Ingestion** (`sources`): upload route stores the file via `shared/storage`, creates a `Source` (`pending`), enqueues `INGEST_TASK` through the `jobs.TaskQueue` protocol *by task name*. Worker `sources/tasks.py` parses → chunks (token-aware via the embedder) → embeds in batches (`passage:` prefix) → in **one transaction** inserts chunks, sets `ready` and calls `sessions.bump_corpus_version`. The slow phase runs with no open transaction/row lock; stale results are dropped if the source was deleted/re-queued. `TransientError` retries with backoff (5×), `PermanentError`/`ParseError` marks `failed`. Tasks must stay idempotent (`task_acks_late=True`).
- **Status push**: every source status change is published to Redis pub/sub (`sources/events.py`); `GET /sessions/{sid}/sources/events` is an SSE stream (snapshot, then per-change events, keepalive). Subscribe happens *before* loading the snapshot to avoid a gap.
- **Chat turn** (`chat/service.py::_prepare`): embed question once (the vector is shared by cache and search) → cache lookup (skipped if `depends_on_history`, cache disabled on the session, or `use_cache=false`) → `retrieval.retrieve` (top-k, filtered by `retrieval_min_score`) → `db.rollback()` to release the connection before the slow LLM call → model call (blocking or SSE `delta`/`citations`/`done`/`error`). Question and answer are saved **together after** the answer exists. Citations are parsed from `[n]` markers in the answer (`n` = chunk rank in the prompt) and stored with snapshots of title/page so they survive source deletion.
- **Semantic cache** (`cache/`): exact normalised-question hash first, then pgvector similarity ≥ `cache_similarity_threshold` plus equal "meaning markers" (`normalize.py`). Entries are keyed by embedding model, LLM model, prompt version, top_k and `corpus_version`. **Lazy revalidation**: if `sessions.corpus_version` moved, the entry is still valid only if no chunk added since is closer to the question than the entry's `kth_score`. A failed cache store never fails the answer.
- **Isolation**: every query filters by `user_id` *and* `session_id`; foreign resources return 404 (not 403). `get_owned_session` dependency loads the session. Chunks are only ever read via `sources` → `retrieval`.
- **Prompting**: `chat/prompts/answer_v2_strict.txt` (only from sources) vs `answer_v2.txt` (hybrid, `allow_general`, labelled general knowledge). `PROMPT_VERSION` must be bumped whenever a prompt or context format changes, because it keys the cache. The model emits sentinel `NEMA_ODGOVORA` for out-of-scope questions; `StreamFilter` hides it from the stream. Latin-script questions force Latin output (`chat/script.py::to_latin`).
- **LLM layer** (`llm/`): `LLMProvider` protocol with `generate` and `stream` (yields `TextDelta` then `Finished`); only Gemini is implemented, selected by `LLM_PROVIDER`. `LLMError` carries a code mapped to HTTP 502/503.
- **Embeddings**: `get_embedder()` is a process-wide singleton (multilingual-e5-small, 384 dims); `FakeEmbedder` exists for tests. The API warms it in a background thread at startup (`WARM_UP_EMBEDDER`).
- **Errors/config/db**: `shared/errors.py` (`AppError` subclasses → `{"error": {"code","message"}}`), `shared/config.py` (pydantic-settings, `.env`; `DATABASE_URL` is rewritten to `postgresql+psycopg://`; `JWT_SECRET` is required and ≥32 chars but absent from `.env.example`), `shared/rate_limit.py` (fixed-window Redis counter), `shared/db.py` (sync SQLAlchemy, UUID PKs, `Base`).
- **Tests** (`tests/conftest.py`): tables are built with `Base.metadata.create_all`, not Alembic, so a model change that lacks a migration will not fail tests. Celery is replaced with `InlineTaskQueue`, embeddings with `FakeEmbedder`. Always add a migration (`alembic/versions/000N_*.py`) alongside model changes.

## Frontend (`frontend/`)

Vite + React 19 + React Router 7, plain CSS (tokens in `src/styles/tokens.css`, per-feature `*.css`), `three` for the landing/room scenes, `react-markdown` + KaTeX for answers (model emits Markdown and LaTeX). Brand name is "Lofinote" (`src/lib/brand.ts`).

- **Concept: lo-fi aesthetic.** The **user is a corgi**, the **responder is a capybara** (`features/chat/animal.ts`, `PixelAnimal.tsx`; the answering animal is switchable and persisted in localStorage). Keep new UI consistent with the lo-fi mood and the palette roles in `tokens.css` (night/day themes are filled through `--c-*` role variables, not literal colour names).
- Feature folders under `src/features/` (`auth`, `sessions`, `sources`, `chat`, `room`, `landing`, `app`); shared UI primitives in `src/components/ui`.
- All HTTP goes through `src/lib/api/client.ts` (Bearer tokens in localStorage, single-flight refresh on 401) and `endpoints.ts`; types in `types.ts` mirror backend schemas — update both when the backend contract changes. SSE (chat `?stream=true`, source status) is parsed by `sse.ts` over `fetch`, not `EventSource`, because the token travels in the Authorization header.
- `docs/frontend-notes.md` lists decisions/TODOs for deploy (cookie auth + CSRF, CORS, nginx SSE settings, trusted proxy headers). Those are backend changes: propose, don't implement.
