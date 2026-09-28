# CLAUDE.md — conventions and quick reference for AI agents

## Commands

### Tests
```bash
python -m pytest tests/ -q --tb=short
```
99 tests, 12 skipped. The 12 skipped are PostgreSQL integration tests that require a
real DB (`test_postgres_store.py`). They skip automatically when `DATABASE_URL` is absent.
Always run the full suite before committing; it completes in ~50 s on a local machine.

### Lint & format
```bash
python -m ruff check backend/ scripts/ tests/      # lint
python -m ruff format backend/ scripts/ tests/     # format
```
Config is in `ruff.toml`. Rules: E, W, F, B. Line length 120.
`E501` (line too long) and `B008` (Depends() in defaults) are suppressed.

### Dead-code check
```bash
python -m vulture backend/ scripts/ vulture_whitelist.py --min-confidence 80 --ignore-names cls
```
`--ignore-names cls` suppresses false positives from Pydantic v2 `@field_validator`
classmethods where `cls` is required by Python's classmethod protocol but not used in the body.
`vulture_whitelist.py` documents other intentional "unused" symbols.

### Pre-commit (one-time setup)
```bash
pip install pre-commit
pre-commit install
```
After installation, `ruff check --fix` and `ruff-format` run automatically on every `git commit`.
Hook versions are pinned in `.pre-commit-config.yaml`; keep the `rev` in sync with the
`ruff==X.Y.Z` pin in `requirements.txt`.

---

## Architecture (abbreviated)

Full architecture is in `ARCHITECTURE.md`. Key points for editing:

- **`backend/app/services/document_store.py`** — single god-object (~2 100 lines). All DB
  access (SQLite by default, PostgreSQL in prod) goes through here. Do not bypass it to
  query the DB directly elsewhere.
- **`backend/app/services/retriever.py`** — 9-signal ranker. Scores are computed on every
  search; nothing is pre-stored. Session-level `cached_embeddings` dict avoids re-embedding
  the same URL twice within a request.
- **`backend/app/services/explainer.py`** — LLM explanation layer. Gemini first, OpenAI
  fallback, static fallback if both absent.
- **`backend/app/routers/`** — thin FastAPI routers. Business logic lives in services.
- **`backend/app/container.py`** — module-level singletons (store, cache, registry, …).
  Import from here; never instantiate services inside routers.

---

## Conventions

### Naming
- SQL column aliases should be descriptive (`document_count`, not `n`).
- Accumulator / return-value variables: use `result`, not `out`.
- Datetime locals parsed from ISO strings: suffix `_dt` (e.g. `last_success_dt`).
- Private methods that do a DB query: prefix with `_get_` or `_fetch_` so the IO is obvious
  at the call site (e.g. `_get_user_display_name`, not `_display_name`).
- Lambda variables in `sorted()` / `.sort()`: use the same name as the surrounding loop
  variable (`doc`, `chunk`), not the generic `item`.

### Helpers extracted during Phase 3 refactor
The following shared helpers exist — use them instead of repeating the pattern:

| Helper | Location | Purpose |
|--------|----------|---------|
| `_check_password_complexity(v)` | `models.py` | Validate password strength in `@field_validator` |
| `DocumentStore._normalize_email(email)` | `document_store.py` | `strip().lower()` for auth emails |
| `DocumentStore._row_to_user(row, email_verified=None)` | `document_store.py` | Convert a `sqlite3.Row` to `AuthUser` |
| `DocumentStore._create_session(conn, user_id)` | `document_store.py` | INSERT into `auth_sessions`, return token |
| `ExplainerService._build_explain_prompt(...)` | `explainer.py` | Build `(system, user)` prompt tuple for both Gemini and OpenAI |

### Models
- Pydantic v2 throughout. Use `model_validate()`, not `parse_obj()`.
- `@field_validator` requires `@classmethod` even when `cls` is not used. Do not remove it.

### Database
- SQLite in dev (`data/retriever.db`), PostgreSQL in prod. The `DocumentStore` abstraction
  handles both; `_connection()` returns a context manager that works for either.
- Schema changes go through Alembic: `python -m alembic revision --autogenerate -m "..."`,
  then `python -m alembic upgrade head`.
- The SQLite schema is also maintained in `_init_db()` inside `document_store.py` for
  test isolation. Keep both in sync — `test_schema_parity.py` enforces this.

### Authentication
- All auth routes live in `backend/app/routers/auth.py`.
- Token auth: `Authorization: Bearer <token>`. Tokens are 32-byte URL-safe secrets stored
  in `auth_sessions` with a 30-day expiry.
- Passwords: PBKDF2-SHA256, 120 000 iterations. Helper: `_hash_password` / `_verify_password`.
- MFA (TOTP) and passkeys (WebAuthn) are implemented but optional.

### Error handling
- Validate only at system boundaries (user input, external APIs). Don't add internal guards.
- FastAPI exception handlers are in `main.py`. Return `{"detail": "..."}` with the right status
  code; don't raise bare `Exception`.

---

## Things to avoid

- **Do not** add `import os` inline with `__import__("os")` — use a top-level import.
- **Do not** repeat `AuthUser(user_id=row[...], ...)` constructions — use `_row_to_user(row)`.
- **Do not** call `source_enabled()` in a per-provider loop — use `get_source_statuses()` once
  and filter with a set.
- **Do not** call `dict.get(key)` twice for the same key in the same expression — assign to a
  local variable or use the walrus operator.
- **Do not** compute a loop-invariant expression (e.g. `" ".join(query.lower().split())`)
  inside a tight loop over docs.
- **Do not** add comments that restate what the code does. Only add a comment when the WHY
  is non-obvious.
