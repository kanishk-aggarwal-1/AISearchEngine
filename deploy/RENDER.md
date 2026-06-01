# Render Deployment Guide

This guide targets a practical hosted setup on Render using:
- one backend web service
- one frontend web service
- one managed Postgres database
- one managed Redis / Key Value instance

## Services to create

### 1. Postgres
Create a managed Postgres database and copy its internal connection string into `DATABASE_URL` for the backend.

### 2. Redis / Key Value
Create a managed Redis-compatible cache and copy its internal connection string into `REDIS_URL`.

### 3. Backend web service
Create a Docker-based web service from this repository.

Use:
- root directory: repository root
- Dockerfile path: `backend/Dockerfile`
- health check path: `/health`

Recommended environment variables:
- `APP_BASE_URL=https://<frontend-domain>`
- `FRONTEND_ORIGIN=https://<frontend-domain>`
- `DATABASE_URL=<managed postgres internal url>`
- `CACHE_BACKEND=redis`
- `REDIS_URL=<managed redis internal url>`
- `RUN_DB_MIGRATIONS_ON_START=true`
- `EMAIL_PREVIEW_TOKENS=false`
- `GEMINI_API_KEY=...` or `OPENAI_API_KEY=...`
- SMTP settings if you want real verification/reset emails
- optional: `QDRANT_URL`, `QDRANT_API_KEY`

Notes:
- the backend container now respects `PORT`
- startup can run `python -m alembic upgrade head` automatically when `RUN_DB_MIGRATIONS_ON_START=true`

### 4. Frontend web service
Create a Docker-based web service from this repository.

Use:
- root directory: repository root
- Dockerfile path: `frontend/Dockerfile`

Recommended environment variables:
- `NEXT_PUBLIC_API_URL=https://<backend-domain>`
- or keep `/api` only if you are placing both services behind a shared reverse proxy

## First production checks

After deploy:
1. Open the backend health endpoint.
2. Open the frontend home page.
3. Register the first account.
4. Run one search in each main category.
5. Confirm bookmarks and saved sessions persist.
6. Confirm Redis-backed caching is active via `/health`.
7. Confirm SMTP behavior matches your settings.

## Recommended Render settings

Backend:
- instance type: start with a small instance for demos
- auto-deploy: enabled
- health check path: `/health`

Frontend:
- auto-deploy: enabled
- use the Dockerfile build

## Operational reminder

Do not rely on SQLite in hosted production. Use:
- managed Postgres for `DATABASE_URL`
- managed Redis for `REDIS_URL`

If you later add a hosted vector database, configure it through `QDRANT_URL` and `QDRANT_API_KEY`.
