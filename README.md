# Medflow — Hospital presence & activity

A full-stack hospital workforce application: Next.js/React/TypeScript, Tailwind, shadcn-style Radix components, Recharts, FastAPI, SQLAlchemy/Alembic, PostgreSQL RLS, Redis, and Celery. Doctor and administrator permissions are enforced in the API and PostgreSQL.

**Three separate runtimes are included.** Single-computer mode saves real manual attendance and activity reports in SQLite using local accounts. The private Sites deployment is a persistent, fictional integration sandbox, backed by D1 and an authenticated-owner namespace; its administrator/doctor selector previews workflows. The enterprise runtime is the Python/PostgreSQL stack under `backend/`; it has no local password endpoints, sandbox role switch, or seeded accounts.

This is an implementation and deployment foundation, not a certification of production readiness or HIPAA compliance. Live SSO/MFA, equipment-specific integration validation, provider agreements, load/security testing, and organizational policy review remain deployment prerequisites. See [release acceptance](docs/ACCEPTANCE.md).

## Use it on a simple computer now

Run `python scripts/run_local.py` (Windows: `py scripts/run_local.py`) and open **http://127.0.0.1:8000/local**. This standalone mode saves real arrival/departure timestamps, calculates duration, and stores activity reports in `data/medflow.sqlite3`. It needs Python only; the core page works without Node, Docker, Redis, a database server, or cloud configuration. First-run setup creates separate local admin and doctor accounts. Records persist across restarts. See the [single-computer guide](docs/LOCAL.md) for API examples and backups.

## Included behavior

- Responsive administrator and doctor dashboards, searchable/filterable directory, doctor detail, attendance timelines, facility/network management, activity review, analytics, audited CSV/PDF exports, and profile preferences.
- Browser audio recording with pause/resume/playback; editable manual transcripts; approval-gated server transcription jobs with private KMS-encrypted S3 storage. No browser speech API silently sends audio elsewhere.
- OIDC Authorization Code + PKCE, nonce/state validation, signed ID-token verification, explicit MFA claims, opaque expiring HttpOnly sessions, origin checks, rate limiting, audit logs, and disabled-account checks.
- HMAC-authenticated RADIUS/normalized-webhook ingestion, enrolled certificate identities, immutable original events, a transactional SQL outbox, retrying workers, and authorized SSE plus polling.
- Replayable UTC reconciliation: duplicate/out-of-order events, AP roaming with stable accounting IDs, multiple-device interval union, reconnection grace, stale evidence caps, outage uncertainty, conflicting buildings, and explicit unknown/transit gaps.
- Correction review, manual unverified attendance, PostgreSQL exclusion constraints against overlapping periods, tenant foreign keys, and forced row-level policies.
- Optional approved-provider AI categorization using exact transcript offsets. Generated excerpts are source-hashed, labeled, reviewable, and invalidated when the transcript changes.
- PWA manifest and offline notice; private records are never cached offline.

## Run and verify

```sh
npm ci
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm run build
npm run test:edge
.venv/bin/pytest -q
```

PostgreSQL integration tests additionally require a **disposable** database. Migrate it first:

```sh
cd backend
DATABASE_URL=postgresql+psycopg://postgres:password@localhost/medflow alembic upgrade head
cd ..
TEST_POSTGRES_URL=postgresql+psycopg://postgres:password@localhost/medflow .venv/bin/pytest -q
```

Copy `.env.example` to `.env`, inject secrets, provision database login roles, migrate, and provision the first administrator as described in [deployment](docs/DEPLOYMENT.md). `docker compose up --build` starts the production services after those prerequisites. The gateway listens on loopback port 8080; place it behind a TLS terminator. There is no insecure development login in this stack.

FastAPI publishes OpenAPI at `/openapi.json` and interactive documentation at `/docs`; a generated copy is included in `docs/openapi.json`. The production reverse proxy can restrict these endpoints to the internal network.

## Project map

| Path | Purpose |
| --- | --- |
| `app/`, `components/` | Next.js interface and accessible UI primitives |
| `backend/app/main.py` | REST APIs, signed ingestion, exports, SSE |
| `backend/app/security.py` | OIDC, sessions, authorization, CSRF/rate limits |
| `backend/app/reconcile.py` | Pure deterministic attendance engine |
| `backend/app/worker.py` | Durable outbox, reconciliation, transcription, retention |
| `backend/alembic/` | Schema, RLS, tenant integrity, exclusion constraints |
| `worker/`, `drizzle/` | Owner-private fictional Sites sandbox only |
| `infra/`, `.github/workflows/` | Containers, DB privileges, CI and ECS promotion |
| `docs/` | Architecture, integrations, deployment, operations, and release acceptance |

## Verification boundaries

Tests exercise API authorization and PostgreSQL itself, including raw SQL access with a non-owner role. They do not establish equipment compatibility, provider medical vocabulary accuracy, legal compliance, or performance at a particular hospital’s event volume. Those require the actual deployment systems and review.
