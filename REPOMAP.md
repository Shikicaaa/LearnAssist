# REPOMAP

Map of the whole repository: where things live, how requests flow, and the backend improvement backlog. Rules for working in this repo are in `CLAUDE.md` (backend is read-only / suggestion-only; frontend is writable).

## Top level

| Path | What it is |
|---|---|
| `app/` | FastAPI backend (modular monolith) |
| `alembic/versions/` | Migrations `0001` pgvector, `0002` users+refresh tokens, `0003` sessions, `0004` sources+chunks, `0005` chat, `0006` cache |
| `tests/` | pytest suite (real Postgres `rag_test` + Redis db 15, fake embedder, inline task queue) |
| `frontend/` | Vite + React 19 + TS client, "Lofinote" lo-fi UI (corgi = user, capybara = responder) |
| `docs/frontend-notes.md` | Deploy/frontend decisions: cookie auth + CSRF, CORS, nginx SSE config, proxy headers |
| `docker-compose.yml` | `db` (pgvector/pg17), `redis`, `api`. **No worker service** |
| `.importlinter` | Module-boundary contracts (`lint-imports`) |
| `data/files` | Local file storage (`LOCAL_STORAGE_PATH`) |

## Backend (`app/`)

Layering, bottom to top (a module may import only the public `__init__.py` of modules below it):

```
shared  ->  auth | jobs | embeddings  ->  sessions  ->  llm  ->  sources  ->  retrieval  ->  cache  ->  chat
```

| Module | Responsibility | Notable files |
|---|---|---|
| `main.py` | App factory, router mounting under `/api/v1`, background embedder warm-up | |
| `worker.py` | Celery entry point; imports `sources` so its tasks register | |
| `shared/` | `config.py` settings, `db.py` engine/Base/mixins, `errors.py` error envelope, `rate_limit.py` Redis fixed window, `storage.py` file storage, `pagination.py`, `health.py` (`/health`, `/ready`) | |
| `auth` | Register/login/refresh/logout/me/change-password; Argon2 + JWT access + rotating refresh tokens | `security.py`, `service.py`, `get_current_user` |
| `sessions` | "Notebooks" (`StudySession`): ownership, quota (`max_sessions_per_user`), `corpus_version`, `cache_enabled`, delete hooks | `get_owned_session`, `bump_corpus_version`, `register_delete_hook` |
| `jobs` | Celery app, `TaskQueue` protocol (`CeleryTaskQueue`, `InlineTaskQueue`), `@task` with retry policy, `TransientError`/`PermanentError` | `queue.py`, `retry.py` |
| `embeddings` | `Embedder` (e5-small, `query:`/`passage:` prefixes, token counting), `FakeEmbedder`, singleton `get_embedder` | `service.py` |
| `llm` | `LLMProvider` protocol, Gemini implementation, `LLMError` codes, dev-only `POST /llm/test` | `gemini.py`, `service.py` |
| `sources` | Upload (files/text), parsers (PDF/DOCX/TXT/MD), chunker, ingest task, SSE status events, pgvector search (`search_chunks`, `best_score_since`, `get_chunk`) | `service.py`, `tasks.py`, `events.py`, `repository.py` |
| `retrieval` | Thin read layer over `sources`: embed question, top-k with `min_score`, `kth_score` for the cache | `service.py` |
| `cache` | Semantic answer cache with lazy revalidation; `POST /sessions/{sid}/cache/clear` | `service.py`, `normalize.py`, `repository.py` |
| `chat` | Ask/stream/history, prompt building, citation parsing, follow-up heuristic, Cyrillic→Latin | `service.py`, `prompts.py`, `citations.py`, `followup.py`, `script.py`, `prompts/*.txt` |

### HTTP surface (`/api/v1` unless noted)

- `GET /health`, `GET /ready` (no prefix)
- auth: `POST /auth/register|login|refresh|logout|change-password`, `GET /auth/me`
- sessions: `POST|GET /sessions`, `GET|PATCH|DELETE /sessions/{sid}`, `POST /sessions/{sid}/cache/clear`
- sources: `POST /sessions/{sid}/sources/files|text`, `GET /sessions/{sid}/sources`, `GET /sessions/{sid}/sources/events` (SSE), `GET /sources/{id}`, `GET /sources/{id}/file`, `POST /sources/{id}/reindex`, `DELETE /sources/{id}`
- chat: `POST /sessions/{sid}/messages[?stream=true]`, `GET|DELETE /sessions/{sid}/messages`, `GET /chunks/{chunk_id}`
- llm: `POST /llm/test` (development only)

### Flow 1: source ingestion

```
POST .../sources/files -> sources.service (validate, dedupe by digest, store file, Source=pending, bump nothing yet)
  -> TaskQueue.enqueue(INGEST_TASK) -> Redis broker -> Celery worker: sources.tasks.ingest_source
       tx1: lock source, delete old chunks, status=processing   -> publish SSE event
       (no tx) parse -> chunk -> embed passages
       tx2: bump corpus_version, insert chunks (added_in_version), status=ready -> publish SSE event
  Browser: GET .../sources/events (SSE via Redis pub/sub) updates the sources panel
```

### Flow 2: a chat question

```
POST /sessions/{sid}/messages
  rate limit (Redis) -> get_owned_session -> ChatService._prepare
    embed question (once)
    cache.lookup? (exact hash -> similar vector + same meaning markers -> _still_valid / lazy revalidation)
       hit  -> save messages (cached=True) -> answer
    retrieval.retrieve (pgvector top-k, min_score filter) ; db.rollback()
    no material -> canned NO_SOURCES ; no relevant chunks & strict -> canned NO_ANSWER
    else LLM generate/stream with numbered <izvor> blocks
  _finish: Latin enforcement, NEMA_ODGOVORA sentinel, extract [n] -> citations
  _save: user msg + assistant msg + citation snapshots (+ cache.store in a savepoint) -> commit
```

## Frontend (`frontend/src`)

| Path | Purpose |
|---|---|
| `main.tsx`, `App.tsx` | Entry, router: `/` landing, `/login`, `/register` (guest only), `/app` + `/app/:sid` (auth required) |
| `lib/api/client.ts` | `request`, `authFetch`, `openStream`; Bearer tokens in localStorage; single-flight refresh |
| `lib/api/endpoints.ts`, `types.ts`, `sse.ts` | Endpoint wrappers, backend-mirroring types, SSE-over-fetch parser |
| `features/auth` | `AuthContext`, `AuthPage`, route guards |
| `features/sessions` | Sidebar, session list, `SessionsContext` |
| `features/sources` | Sources panel, upload modal, `useSources` (snapshot + SSE) |
| `features/chat` | `ChatView`, `Composer`, `MessageBubble`, `MarkdownMessage` (KaTeX), `CitationModal`, `useChat` (stream), `PixelAnimal`, `animal.ts` (corgi/capybara) |
| `features/room` | Canvas lo-fi room scene, `CornerCorgi` |
| `features/landing` | Landing page + three.js `HeroScene` |
| `features/app` | `AppShell`, `SessionWorkspace`, `WelcomePage` |
| `components/ui` | Button, Field, Modal, Menu, ThemeToggle, Icons, Logo |
| `styles/tokens.css`, `global.css` | Palette roles (`--c-*`), night/day themes |

## Backend improvement backlog (suggestions only, nothing implemented)

Ordered by value. Each item states the *why*; the user wants the reasoning, so expand it in chat when discussing.

1. **Add a `worker` service to `docker-compose.yml`.** Uploads stay `pending` forever without a Celery worker; compose only defines `api`. Same image, `command: celery -A app.worker worker`, same env. Also add `JWT_SECRET` to `.env.example` (required, ≥32 chars, currently missing, so a fresh clone fails at startup).
2. **Ingestion semantics vs. cache correctness.** `bump_corpus_version` happens on source ready; confirm deleting a source also bumps the version or deletes cache entries citing its chunks (the `cited_chunks` count check covers cited chunks, but a deleted *uncited* chunk can still change what the top-k would be). Needs a test.
3. **Migrations vs. tests drift.** Tests use `create_all`, so a missing migration goes unnoticed. Add a test (or CI step) that runs `alembic upgrade head` on an empty DB and compares with `Base.metadata` (`alembic check`).
4. **Chat runs sync endpoints on the threadpool.** Streaming responses hold a worker thread for the whole generation. Fine at current scale; under load, move chat to async or cap concurrency. Rate limit is per user only, so add a global/provider-level limiter before using a free Gemini tier with several users.
5. **Auth hardening before real deployment** (already scoped in `docs/frontend-notes.md`): httpOnly cookie for the refresh token, CSRF/Origin check, CORS with credentials, trusted proxy headers for rate-limit IPs. Current frontend keeps both tokens in localStorage (XSS-exposed).
6. **Retrieval quality (phase 7).** Calibrate `retrieval_min_score` (0.75) and `cache_similarity_threshold` (0.95; README says 0.93) on real question pairs; add recall@k / MRR eval set. Consider hybrid search (pgvector + Postgres full-text) and an HNSW index check on `chunks.embedding` (verify in `0004`).
7. **Missing providers/features from the plan:** Claude/Ollama/OpenAI-compatible providers behind `LLMProvider`, quizzes (`artifacts` module) with `params_hash` cache, OCR for scanned PDFs, SSE auth expiry policy.
8. **Observability:** structured logs with request id, token usage aggregation (already stored per message: `tokens_in/out`), and a `/ready` check that includes Redis and the embedder state.
9. **README refresh:** file tree and endpoints list are outdated; the Dockerfile still `COPY`s `README.md` (it is staged as deleted in git, so image builds will break if it is actually removed).
