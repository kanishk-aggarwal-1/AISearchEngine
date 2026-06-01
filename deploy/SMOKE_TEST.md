# Production Smoke Test

Use this checklist after any hosted deploy or production-style Docker rollout.

## API readiness
1. `GET /health`
2. `GET /health/deep`
3. Confirm deep health reports expected statuses for:
   - database
   - cache
   - llm
   - vector
   - ingestion
4. Confirm:
   - `ok=true`
   - `cache_backend` is what you expect
   - `redis_enabled` and `redis_connected` are correct
   - `gemini_enabled` or `openai_enabled` match your env

## Database readiness
1. Confirm the backend started without migration errors.
2. Register a test account.
3. Log in and call `GET /auth/me`.
4. Save a bookmark and a session.
5. Restart the backend and confirm data persists.

## Search workflow
1. Search `latest breakthroughs in AI agents`.
2. Search `middle east conflict`.
3. Search `latest NBA updates`.
4. Confirm:
   - results are returned
   - explanation provider is expected
   - sources are shown
   - follow-up works on the saved context

## Admin / ingestion
1. Open `/admin/dashboard` with an admin token.
2. Confirm source status appears.
3. Trigger `POST /ingest/run`.
4. Confirm source counts update.

## Alerts / email
1. Configure alert delivery.
2. Create one alert.
3. Trigger a matching search or ingestion cycle.
4. Confirm webhook/email behavior matches configuration.

## Frontend checks
1. Load the home page.
2. Open one category page.
3. Open one topic page.
4. Confirm save/bookmark/alert actions work from the main flow.

## Deployment checks
1. Confirm reverse proxy routing if using `/api`.
2. Confirm HTTPS termination works.
3. Confirm logs show no migration loop or repeated startup failures.
4. Confirm rate limiting still returns clean JSON responses.
