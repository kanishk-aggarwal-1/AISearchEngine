# Application review and implementation status

## Current structure

- `backend/app/routers`: versioned FastAPI endpoints for auth, users, search, research, sports, admin, browse, and health.
- `backend/app/services`: storage, retrieval/ranking, explanations, alerts/email, caching, scheduling, metrics, WebAuthn, and security controls.
- `backend/app/sources`: arXiv, OpenAlex, Crossref, RSS, NewsAPI, and TheSportsDB adapters.
- `frontend/app`, `components`, `hooks`: Next.js application routes, UI modules, and API state/workflows.
- `alembic/versions`: production schema history; migrations `0004` through `0010` cover feedback, identity, collections, delivery, conversations, scheduler leases, OAuth, and passkeys.
- `tests`, `eval`, `scripts`: backend/frontend tests, retrieval evaluation, smoke checks, and a concurrent search load probe.

## Findings addressed

1. Identity and account lifecycle: explicit admin bootstrap, reset-token privacy, MFA, email changes, data export/deletion, Google OAuth, passkeys, session revocation, and ownership enforcement.
2. Collections and lifecycle: bookmark folders/tags/notes, alert and follow CRUD, search-history cleanup, session deletion/opening, and offset pagination with UI load-more controls.
3. Alert delivery: SMTP and webhook channels, timezone-aware daily scheduling, delivery history, retries/dead-letter status, and outbound URL validation.
4. Search experience: advanced domain/author/credibility/language/region/date filters, streamed explanations, cancellation, citation warnings, persistent conversations, and expiring read-only share links.
5. Domain depth: team/player/roster endpoints, indexed injury/transaction updates, schedule/standings, Crossref/OpenAlex/arXiv research aggregation, BibTeX, citation graphs, and licensed open-access links.
6. Engineering: Redis-aware distributed controls with a database scheduler lease fallback, migration parity tests, Postgres/Redis CI services, security regression tests, frontend type/build tests, and `scripts/load_search.py`.

## Operational configuration still required

These are deployment inputs rather than missing code:

- Set `GOOGLE_OAUTH_CLIENT_ID` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` to enable Google sign-in.
- Set `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` to the production hostname and HTTPS origin before registering production passkeys.
- Configure SMTP for real alert/account email; without it the development preview behavior applies.
- Configure provider keys and infrastructure (`OPENAI_API_KEY` or `GEMINI_API_KEY`, NewsAPI, Redis, Postgres, and optional Qdrant) for the corresponding production paths.
- Injury and transaction results come from indexed sports coverage because TheSportsDB's free interface does not provide a complete official injury/transaction feed. Full text is linked only when OpenAlex reports a lawful open-access location.
