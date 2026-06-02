# Render Backend Setup Reference

## Start Command

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 4
```

### Breakdown:
- **`uvicorn`** — ASGI web server (required for FastAPI)
- **`backend.app.main:app`** — Module path and app instance
- **`--host 0.0.0.0`** — Listen on all interfaces (required for Render)
- **`--port $PORT`** — Use Render's PORT environment variable (default 8000)
- **`--workers 4`** — Run 4 worker processes for better concurrency

## Build Command

```bash
pip install -r requirements.txt && python -m alembic upgrade head
```

### Breakdown:
1. **Install dependencies** from requirements.txt
2. **Run database migrations** (creates tables, indexes, etc.)
3. Ready to start

## Environment Variables (Required)

| Variable | Source | Example |
|----------|--------|---------|
| `DATABASE_URL` | Neon PostgreSQL | `postgresql://user:pass@host/dbname` |
| `REDIS_URL` | Upstash Redis | `redis://:pass@host:port` |
| `FRONTEND_ORIGIN` | Vercel URL | `https://your-app.vercel.app` |
| `CACHE_BACKEND` | Set to `redis` | `redis` |
| `RUN_DB_MIGRATIONS_ON_START` | Set to `true` | `true` |

## Health Check

Render will automatically monitor:
```
GET /health
```

If this returns 200 OK, your backend is healthy.

## Logs

View logs in Render dashboard:
1. Go to your service
2. Click **Logs** tab
3. Or enable **Tail Logs** for real-time

## Testing Locally Before Deploy

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations (with local SQLite)
python -m alembic upgrade head

# Start server
uvicorn backend.app.main:app --reload --port 8000

# Test health endpoint
curl http://localhost:8000/health
```

## Common Issues

### "ModuleNotFoundError: No module named 'backend'"

**Solution**: Make sure PYTHONPATH includes the project root.
- Render automatically handles this, but check that your repo structure is:
  ```
  AISearchEngine/
    ├── backend/
    ├── frontend/
    ├── requirements.txt
  ```

### "psycopg.Error: FATAL: remaining connection slot reserved"

**Cause**: Too many concurrent connections to PostgreSQL.
**Solution**: Reduce `--workers` from 4 to 2, or upgrade Neon plan.

### "redis.ConnectionError"

**Cause**: REDIS_URL is wrong or Upstash is down.
**Solution**: 
1. Verify REDIS_URL from Upstash console
2. Check Upstash status: https://upstash.com/status

### "Alembic upgrade failed"

**Cause**: Database migrations have errors.
**Solution**:
1. Check Render logs for specific error
2. Run locally first: `python -m alembic upgrade head`
3. Fix migration file if needed

## Scaling

| Issue | Solution |
|-------|----------|
| High latency | Increase `--workers` to 8 |
| Out of memory | Decrease `--workers` to 2 |
| DB connection errors | Upgrade Neon tier |
| Redis throttled | Upgrade Upstash tier |

## Production Checklist

- [ ] FRONTEND_ORIGIN set to your Vercel domain
- [ ] DATABASE_URL verified (test connection locally)
- [ ] REDIS_URL verified (test connection locally)
- [ ] `RUN_DB_MIGRATIONS_ON_START=true`
- [ ] `LOG_FORMAT=json` for production
- [ ] Health endpoint responds 200 OK
- [ ] Frontend can reach backend (check CORS headers)
