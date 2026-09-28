# Architecture

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, Pydantic v2, Uvicorn |
| Frontend | Next.js 14 (App Router), TypeScript, React hooks |
| Primary DB | SQLite (default) or Postgres (opt-in via `DATABASE_URL`) |
| Cache | Redis (primary) with in-process fallback |
| Vector index | Qdrant (optional) |
| Embeddings | Gemini `gemini-embedding-001` → OpenAI `text-embedding-3-small` → hash fallback |
| LLM | Gemini `gemini-2.5-flash` → OpenAI `gpt-4.1-mini` → rule-based fallback |
| Schema migrations | Alembic (Postgres) / inline `_init_db` + `_migrate_*` (SQLite) |

---

## Backend module map

```
backend/app/
├── main.py              Entry point: FastAPI app, middleware (CORS, rate-limit,
│                        security headers, metrics), lifespan (scheduler start/stop)
├── config.py            Pydantic Settings; reads .env
├── container.py         Singleton service instances; imported by all routers
├── dependencies.py      FastAPI auth helpers: bearer_token, current_user,
│                        require_own_user, current_admin, resolve_search_user
├── models.py            All Pydantic request/response models (~45 classes)
│
├── routers/
│   ├── auth.py          /v1/auth/* — register, login, logout, passkeys, TOTP, OAuth,
│   │                     password reset, email verification, email change, data export
│   ├── users.py         /v1/users/{id}/* and /v1/me/* — profile, follows, alerts,
│   │                     alert-delivery, bookmarks, search history, saved sessions
│   ├── search.py        /v1/search, /v1/search/stream (SSE), /v1/followup,
│   │                     /v1/compare, /v1/conversations/*, /v1/contexts/*, /v1/shared/*
│   ├── browse.py        /v1/headlines, /v1/category/*, /v1/trending, /v1/topic/*
│   ├── admin.py         /v1/admin/* and /v1/ingest/* — admin dashboard, source toggle,
│   │                     ingestion triggers (requires is_admin)
│   ├── health.py        /ping, /health, /health/deep, /metrics, /metrics/summary,
│   │                     /metrics/prometheus (unversioned, no auth)
│   ├── sports.py        /v1/sports/* — sports-specific insight and dashboard endpoints
│   └── research.py      /v1/research/* — paper search, explain, compare
│
└── services/
    ├── document_store.py  SQLite store: 102 methods covering all persistence (auth,
    │                       search, bookmarks, alerts, sessions, ingestion state,
    │                       caching, conversations, scheduler locks). ~2100 lines.
    ├── postgres_store.py  Postgres variant of DocumentStore (~16 methods — partial
    │                       coverage only; SQLite store is the primary implementation)
    ├── store_factory.py   Picks SQLite vs Postgres store at startup
    ├── cache_service.py   Redis-backed cache with in-process dict fallback; handles
    │                       query cache, headline cache, rate-limit counters, locks
    ├── retriever.py       Query analysis (intent detection, rewriting, expansion),
    │                       doc ranking (9-signal scorer), chunk ranking, diversification
    ├── embedding_service.py  Gemini/OpenAI embeddings with hash-based fallback
    ├── enrichment_service.py Enriches docs with credibility score, citation snippet,
    │                          freshness label, entity tags, bias, sports/research metadata;
    │                          contradiction detection, timeline, comparison
    ├── explainer.py       Gemini/OpenAI LLM explanation with structured JSON output;
    │                       follow-up Q&A; fallback rule-based explanation
    ├── ingestion.py       Orchestrates live multi-source fetch → enrich → upsert
    ├── source_registry.py Manages source adapters; fan-out gather across categories
    ├── alert_service.py   Alert evaluation, delivery (webhook + email digest)
    ├── scheduler.py       asyncio.Task loop; distributed lock prevents duplicate runs
    ├── metrics_store.py   Redis-backed search metrics (latency, cache hit rate,
    │                       citation coverage) with 2s in-process summary cache
    ├── observability_service.py In-memory counters/histograms; Prometheus text export
    ├── login_throttle.py  Redis (or in-process) brute-force lockout per email
    ├── passkey_service.py WebAuthn registration + authentication
    ├── totp_service.py    TOTP secret generation and code verification (pyotp)
    ├── email_service.py   SMTP email with preview-token mode for local dev
    ├── webhook_security.py SSRF-safe webhook URL validation
    ├── logging_service.py Structured logging; JSON format for production
    └── vector_index_service.py Qdrant upsert + search; no-op when unconfigured

sources/
├── base.py      BaseSource ABC
├── newsapi.py   NewsAPI.org adapter
├── rss.py       Generic RSS/Atom fetch
├── arxiv.py     arXiv API
├── crossref.py  Crossref DOI/metadata
├── openalex.py  OpenAlex open-access papers
└── sports.py    Sports-specific RSS feeds
```

---

## Data flow

### Search request (POST /v1/search)
```
Client → security_middleware (rate limit + headers)
       → metrics_middleware (latency tracking)
       → search() router
           → resolve_search_user() [auth optional]
           → _search_core()
               1. Load user profile + follows (asyncio.to_thread)
               2. analyze_query() → rewrite + intent detection
               3. Build cache key
               4. Redis cache hit? → return immediately
               5. SQLite cache hit? → promote to Redis, return
               6. registry.gather() → live fetch from all sources
               7. enricher.enrich() → credibility/freshness/entities/snippets
               8. vector_index.search() → Qdrant top-k (if enabled)
               9. store.all_recent_documents() → SQLite candidate pool
              10. Merge live + vector + SQLite docs, deduplicate by canonical URL
              11. store.search_chunks() + retriever.rank_chunks() → chunk scoring
              12. retriever.rank() → 9-signal scorer + diversification → top_k docs
              13. explainer.explain() → LLM explanation from top 10 doc context
              14. Save context + history (asyncio.to_thread)
              15. Write to Redis + SQLite cache
              16. metrics_store.record_search()
       → SearchResponse
```

### Ingestion (background scheduler)
```
SchedulerService._run_loop() every 60 min
  → acquire_lock (Redis or SQLite)
  → ingestion.ingest_seed_topics()
      → registry.gather(topic, categories)
          → BaseSource.fetch() per adapter (NewsAPI, RSS, arXiv, etc.)
      → enricher.enrich()
      → store.upsert_documents() + vector_index.upsert_documents()
      → store.finish_ingestion_run()
```

---

## Entry points

| Entry point | How to run |
|---|---|
| Backend API | `uvicorn backend.app.main:app --reload` |
| Frontend | `cd frontend && npm run dev` |
| Tests | `python -m pytest tests/` |
| Linter | `python -m ruff check backend/ tests/` |
| Migrations | `alembic upgrade head` (Postgres only) |

---

## Key design decisions

- **No ORM**: raw SQL throughout `document_store.py` and `postgres_store.py`
- **DocumentStore is a god object**: all persistence (auth, search, bookmarks, alerts, ingestion, caching, conversations) lives in one 2100-line class
- **Dual store**: SQLite and Postgres share an interface but are maintained separately; Postgres coverage is partial
- **In-process fallbacks everywhere**: embeddings, cache, rate limiting, and scheduler locks all degrade gracefully when external services are unavailable
- **No LangChain**: ranking pipeline is custom so scoring weights can be tuned per-signal
