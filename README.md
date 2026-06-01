# SignalScope AI

SignalScope AI is a full-stack AI search and retrieval platform for:
- tech news
- research papers
- sports coverage
- general and world news

It combines live source ingestion, hybrid retrieval, chunk-aware grounding, and LLM-backed explanation so users can search what is happening, understand why it matters, and keep track of topics over time.

## What The App Does

SignalScope AI lets users:
- search across multiple source types in one interface
- retrieve and rank relevant articles or papers using hybrid signals
- generate grounded explanations, timelines, comparisons, and follow-up answers
- browse latest headlines by category
- save bookmarks, alerts, follows, history, and search sessions
- inspect sports and research-specific detail pages
- manage source health and source toggles from an admin dashboard

## Core Features

### Search and RAG
- Hybrid retrieval using semantic, lexical, recency, credibility, personalization, exact-phrase, coverage, and chunk-support signals
- Chunk-aware indexing and passage retrieval for better grounding
- Query rewriting for broad or vague queries
- Query expansion for common aliases like `AI`, `NBA`, `paper`, and `conflict`
- Source diversity reranking to reduce repetitive top results from the same outlet
- Grounded explanations with inline source references
- Follow-up chat over saved context
- Compare mode for query-vs-query analysis
- Timeline generation from retrieved sources
- No-result recovery suggestions

### Explanation controls
- Modes: `tldr`, `beginner`, `deep`, `analyst`
- Formats: `standard`, `bullet`, `pros_cons`, `timeline`, `fact_check`

### Coverage
- Tech feeds
- Research feeds and arXiv
- Sports headlines and event-style data
- General/world news feeds

### User workspace
- Register/login session flow
- Logout
- Email verification with SMTP delivery when configured, plus preview fallback for local development
- Password reset with SMTP delivery when configured, plus preview fallback for local development
- Search history
- Saved sessions
- Follows/watchlist
- Alerts
- Bookmarks
- Alert delivery settings and webhook preview/test

### Category and topic views
- Latest headlines homepage
- Category landing pages
- Topic pages
- Sports dashboard
- Sports team detail pages
- Research workspace
- Research paper detail pages

### Platform and operations
- Scheduled ingestion
- Event-driven ingestion webhook
- Scheduled alert delivery
- Redis-backed caching with SQLite fallback
- Ingestion run history and source freshness tracking
- Source health tracking
- Source enable/disable controls
- Admin dashboard
- Metrics and Prometheus export
- Structured logging
- Rate limiting and security headers
- Docker, Docker Compose, and GitHub Actions CI
- Production-style Docker setup with `next build` + `next start`
- Nginx reverse proxy config for `/api` routing
- Optional vector search with Qdrant
- Gemini/OpenAI support with fallback behavior

## Tech Stack

### Frontend
- Next.js
- React
- Custom CSS in `frontend/app/globals.css`

### Backend
- FastAPI
- Pydantic
- httpx

### Data and caching
- Postgres or SQLite for documents, chunks, users, sessions, bookmarks, alerts, source health, and fallback cache
- Redis for primary cache

### AI and retrieval
- Gemini API
- OpenAI API
- Hybrid retrieval and chunk-aware ranking
- Optional Qdrant vector backend

### DevOps
- Docker
- Docker Compose
- Nginx
- GitHub Actions CI

## Project Structure

```text
SearchEngine/
+-- backend/
|   +-- app/
|       +-- main.py
|       +-- models.py
|       +-- services/
|       +-- sources/
+-- frontend/
|   +-- app/
|       +-- page.js
|       +-- category/[slug]/page.js
|       +-- topic/[topic]/page.js
|       +-- sports/[team]/page.js
|       +-- research/[paperId]/page.js
+-- deploy/
|   +-- nginx.conf
+-- tests/
+-- requirements.txt
+-- docker-compose.yml
+-- docker-compose.prod.yml
+-- README.md
```

## Run Locally

## Database Modes

SignalScope AI supports two persistence modes:

- `SQLite` for lightweight local development and tests
- `Postgres` for production-style local runs and deployment

Database selection is environment-driven:

- set `DATABASE_URL` to use Postgres
- leave `DATABASE_URL` empty to use `SQLITE_DATABASE_PATH`

Examples:

```env
DATABASE_URL=
SQLITE_DATABASE_PATH=data/retriever.db
```

```env
DATABASE_URL=postgresql://signalscope:signalscope@localhost:5432/signalscope
SQLITE_DATABASE_PATH=data/retriever.db
```

### 1. Start Redis

If Redis is installed locally:

```powershell
redis-server
```

If you do not want Redis for local development, set this in `.env`:

```env
CACHE_BACKEND=sqlite
```

### 2. Start the backend

From the project root:

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python -m pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m uvicorn backend.app.main:app --reload
```

Backend docs:
- `http://127.0.0.1:8000/docs`

If `DATABASE_URL` is blank, `alembic upgrade head` targets the SQLite file from `SQLITE_DATABASE_PATH`.

### 2a. Run locally with Postgres

Start a local Postgres instance, set:

```env
DATABASE_URL=postgresql://signalscope:signalscope@localhost:5432/signalscope
```

Then run:

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python -m pip install -r requirements.txt
copy .env.example .env
alembic upgrade head
python -m uvicorn backend.app.main:app --reload
```

### 3. Start the frontend

In a second terminal:

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine\frontend
npm install
npm run dev
```

Frontend:
- `http://localhost:3000`

### 4. Start the full local stack with Docker

```powershell
docker compose up --build
```

This stack includes Postgres, Redis, backend, and frontend. The backend container runs `alembic upgrade head` before starting the API.

### 5. Start the production-style local stack

This uses the production frontend container, backend container, Redis, and nginx reverse proxy:

```powershell
docker compose -f docker-compose.prod.yml up --build
```

In this mode:
- frontend traffic is served through nginx
- backend API traffic is proxied through `/api`
- the app can run without hardcoding a localhost API URL in the browser
- Postgres migrations run automatically before backend startup

## Environment Variables

Example `.env`:

```env
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=
NEWSAPI_KEY=
APP_BASE_URL=http://localhost:3000
FRONTEND_ORIGIN=http://localhost:3000
DATABASE_URL=
SQLITE_DATABASE_PATH=data/retriever.db
PORT=8000
RUN_DB_MIGRATIONS_ON_START=false
STRICT_REAL_EMBEDDINGS=false
QDRANT_URL=
QUERY_CACHE_MINUTES=20
CACHE_BACKEND=redis
REDIS_URL=redis://localhost:6379/0
REDIS_PREFIX=signalscope
EMAIL_PREVIEW_TOKENS=true
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=SignalScope AI
SMTP_USE_TLS=true
SMTP_USE_SSL=false
EXTRA_FRONTEND_ORIGINS=http://127.0.0.1:3000
RATE_LIMIT_PER_MINUTE=90
```

Notes:
- `DATABASE_URL` takes precedence over `SQLITE_DATABASE_PATH`.
- Postgres URLs should look like `postgresql://user:password@host:5432/database`.
- `FRONTEND_ORIGIN` should point at the public frontend URL that is allowed to call the backend.
- `PORT` is mainly relevant in hosted container environments; both backend and frontend containers now honor it.
- `RUN_DB_MIGRATIONS_ON_START=true` is useful for Docker and hosted deployments where you want schema upgrades applied automatically.
- `CACHE_BACKEND=redis` enables Redis caching.
- If Redis is unavailable, the app falls back to SQLite cache reads and writes.
- `CACHE_BACKEND=sqlite` forces SQLite-only cache behavior.
- If `QDRANT_URL` is empty, vector search is skipped.
- If no LLM key is set, the app uses its fallback explainer and fallback embedding path where allowed.
- If `SMTP_HOST` and `SMTP_FROM_EMAIL` are configured, verification and password reset emails are sent over SMTP.
- If SMTP is not configured, preview tokens remain available for local development when `EMAIL_PREVIEW_TOKENS=true`.

## Default Local Auth Behavior

For local development:
- the first registered account becomes an admin account
- SMTP is optional; when it is absent, verification and password reset stay available through preview tokens
- when SMTP is configured, the same endpoints send real emails and can still expose preview tokens if `EMAIL_PREVIEW_TOKENS=true`

This keeps the full auth lifecycle testable without external mail infrastructure.

## Database Migrations

The project uses Alembic for schema creation and upgrades.

Common commands:

```powershell
alembic upgrade head
alembic downgrade -1
```

For a fresh Postgres database, `alembic upgrade head` creates the full schema from scratch.

## Deployment Readiness

Production-friendly deployment assets now include:
- env-driven backend and frontend containers
- Postgres-aware Docker Compose files
- Redis-aware cache configuration
- automatic migration startup for containerized environments when enabled
- production healthchecks in the Compose stack

Helpful deployment files:
- `deploy/production.env.example`
- `deploy/RENDER.md`
- `deploy/SMOKE_TEST.md`

### Minimum production environment variables

Core runtime:
- `APP_BASE_URL`
- `FRONTEND_ORIGIN`
- `DATABASE_URL`
- `CACHE_BACKEND`
- `REDIS_URL`

AI providers:
- `GEMINI_API_KEY` or `OPENAI_API_KEY`

Auth / email:
- `EMAIL_PREVIEW_TOKENS=false`
- SMTP variables if you want real verification and password reset emails

Optional retrieval infra:
- `QDRANT_URL`
- `QDRANT_API_KEY`

### Auth note

The current auth model uses opaque bearer tokens persisted in the database. There is no separate JWT signing secret in the current architecture, so hosted security depends on:
- HTTPS/TLS
- secure environment variable handling
- database protection
- correct frontend/backend origin configuration

### Production smoke tests

After any hosted deployment, run the checklist in `deploy/SMOKE_TEST.md`.

### Health endpoints

- `GET /health` stays lightweight for container/platform health checks
- `GET /health/deep` returns structured dependency readiness for:
  - database
  - Redis/cache
  - LLM configuration
  - vector backend
  - latest successful ingestion timestamp

## Main API Endpoints

### Core
- `GET /health`
- `GET /health/deep`
- `POST /search`
- `POST /compare`
- `POST /followup`

### Auth and personal workspace
- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /auth/request-verification`
- `POST /auth/verify-email`
- `POST /auth/request-password-reset`
- `POST /auth/reset-password`
- `GET /me/search-history`
- `GET /me/saved-sessions`
- `POST /me/saved-sessions/{context_id}`
- `GET /me/watchlist`

### Headlines and navigation
- `GET /headlines`
- `GET /headlines/{category}`
- `GET /category/{category}`
- `GET /trending`
- `GET /topic/{topic}`

### Ingestion
- `POST /ingest/run`
- `POST /ingest/webhook`

### User features
- `GET /users/{user_id}/profile`
- `PUT /users/{user_id}/profile`
- `GET /users/{user_id}/follows`
- `POST /users/{user_id}/follows`
- `GET /users/{user_id}/alerts`
- `POST /users/{user_id}/alerts`
- `GET /users/{user_id}/alert-delivery`
- `PUT /users/{user_id}/alert-delivery`
- `POST /users/{user_id}/alert-delivery/test`
- `GET /users/{user_id}/bookmarks`
- `POST /users/{user_id}/bookmarks`
- `DELETE /users/{user_id}/bookmarks/{bookmark_id}`

### Domain workspaces
- `GET /sports/insights`
- `GET /sports/dashboard`
- `GET /sports/team/{team}`
- `GET /research/insights`
- `GET /research/papers`
- `GET /research/paper/{paper_id}`
- `POST /research/explain-paper`
- `POST /research/compare-papers`

### Admin and observability
- `GET /admin/dashboard`
- `GET /admin/sources`
- `GET /admin/ingestion-runs`
- `POST /admin/reingest`
- `PUT /admin/sources/{source_name}`
- `GET /metrics`
- `GET /metrics/prometheus`

## Frontend Routes

- `/`
- `/category/[slug]`
- `/topic/[topic]`
- `/sports/[team]`
- `/research/[paperId]`

## First Run Checklist

1. Open `http://127.0.0.1:8000/health`
2. Open `http://localhost:3000`
3. Register your first account
4. Confirm it shows as admin
5. Run a search such as:
   - `latest breakthroughs in AI agents`
   - `middle east conflict`
   - `latest NBA updates`
6. Save a bookmark
7. Save a session
8. Open the admin panel and verify source statuses load

## Retrieval Evaluation

SignalScope AI now includes an offline retrieval evaluation harness so search quality can be measured without requiring paid provider calls.

Dataset:
- `eval/eval_queries.json`

Runner:
- `scripts/run_eval.py`

What it reports:
- `Recall@5`
- `Recall@10`
- `MRR`
- `nDCG@10`
- source diversity at top 5
- citation coverage at top 5
- no-result rate

Supported retrieval configurations:
- `lexical_only`
- `semantic_only`
- `hybrid`
- `hybrid_reranked`
- `hybrid_source_diversity`

Run it locally:

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python scripts\run_eval.py
```

Outputs:
- `eval/out/retrieval_eval_report.json`
- `eval/out/retrieval_eval_report.md`

Notes:
- the harness uses fallback embeddings by default so it stays reproducible and offline-friendly
- add `--allow-provider-calls` only if you explicitly want to compare provider-backed embeddings

## Observability and Operations

Operational visibility now comes from three places:

1. Lightweight health:
- `GET /health`

2. Deep readiness:
- `GET /health/deep`
- includes database, cache, LLM config, vector backend, and last successful ingestion timestamp

3. Runtime metrics:
- `GET /metrics`
- `GET /metrics/prometheus`

Useful signals now include:
- search request counts
- search latency
- retrieval latency
- chunk ranking latency
- explanation latency
- follow-up latency
- cache hit/miss counts
- no-result query count
- alert delivery success/failure and latency
- reingest metrics
- source freshness summary

Admin operations now also expose:
- source health with success/failure counts and average latency
- recent ingestion runs
- manual topic reingest

## Core Architecture

SignalScope AI is organized around a production-style retrieval pipeline:

1. Source acquisition
- RSS feeds, research APIs, sports/event sources, and scheduled/webhook ingestion

2. Persistence
- Postgres for production-style deployments
- SQLite fallback for lightweight local development and tests
- Redis for primary query caching

3. Retrieval
- live retrieval + stored document retrieval + optional vector retrieval
- query rewriting and query expansion
- hybrid ranking with semantic, lexical, recency, credibility, coverage, title-match, and diversity signals
- chunk-aware support for stronger grounding

4. Explanation
- Gemini or OpenAI when configured
- deterministic fallback explainer when they are not

5. Product workflow
- search
- grounded answer
- source inspection
- compare
- save context
- follow-up
- alert creation

See also:
- `docs/ARCHITECTURE.md`
- `docs/CASE_STUDY.md`
- `docs/DEMO_SCRIPT.md`

## Validation

### Backend tests

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python -m unittest discover -s tests -p "test_*.py" -v
```

### Frontend production build

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine\frontend
npm run build
```

### Production-style Docker verification

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
docker compose -f docker-compose.prod.yml config
```

### Migration verification

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python -m alembic upgrade head
```

### Retrieval eval

```powershell
cd C:\Users\Kanishk\Desktop\SearchEngine
python scripts\run_eval.py
```

## Current Status

SignalScope AI is a feature-rich advanced MVP with:
- validated backend tests
- validated frontend production build
- end-to-end search, auth, admin, sports, and research flows
- SMTP-ready auth mail flows
- production-shaped Docker assets for reverse-proxy deployment

The next layer beyond this is deeper hosted-production work:
- managed Postgres/Redis/Qdrant
- external email provider operations and monitoring
- cloud-specific secrets/TLS/runtime hardening
- secret management
- cloud hosting and TLS
- external email provider operations
- provider-specific scaling and monitoring
