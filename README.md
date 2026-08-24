# FlowForge AI — Distributed Job Orchestration Platform

FlowForge AI is a multi-tenant background job scheduling and orchestration
system: projects submit jobs to named queues, workers claim and execute them,
and failures are tracked through retries into a dead-letter queue for
inspection and manual replay. It ships with a FastAPI control-plane API and a
React operator console for managing everything through a browser.

**Live repo:** https://github.com/chandupatil07/flowforge-ai

---

## What's implemented

**Auth & multi-tenancy**
- Username/password registration and login (bcrypt-hashed passwords, JWT access tokens)
- Projects, with automatic OWNER membership for the creator
- Role-based access control per project — `OWNER`, `DEVELOPER`, `OPERATOR` — enforced on every route
- Project isolation: a user with no membership on a project gets a 403, not a 404 leak

**Queues & jobs**
- Queue creation with a per-queue concurrency limit
- Job submission with payload validation (100 KB cap), priority, retry count, and delay-based scheduling
- Idempotency-key support — resubmitting with the same key returns the original job instead of creating a duplicate
- Job listing with status/queue filters, single-job lookup, and cancellation

**Reliability**
- Dead-letter queue: list failed jobs and requeue them with attempts reset
- Batch jobs: submit a group of jobs as one unit and track combined progress
- Cron-style recurring job configuration (create/delete)
- Worker registration, heartbeats, and listing (liveness tracking)
- AI-diagnostics read endpoint, for surfacing root-cause analysis against a failed job

**Frontend**
- React + TypeScript + Vite operator console: register/login, create projects, manage queues,
  submit and monitor jobs, work the DLQ, create batches and cron schedules, and view registered workers

## What's not implemented yet

- The distributed worker execution loop (atomic claiming under concurrency, subprocess isolation,
  timeout enforcement, fencing tokens) has scaffolding in `flowforge_ai/execution_plane/` but is not
  yet verified under concurrent load.
- The AI diagnostics *engine* (the piece that actually analyzes a failure and writes a diagnosis) is
  not built — only the read endpoint for an already-written diagnosis exists.
- The cron scheduler doesn't yet evaluate expressions and enqueue jobs on its own; it only stores schedules.
- Automated test coverage is limited to auth + project isolation (`tests/test_stage1.py`). Queue, job,
  batch, cron, and worker routes are exercised manually but don't have a test suite yet.
- No Docker/Compose setup — this runs directly with `uvicorn` and a Postgres (or SQLite) connection string.

Being upfront about this list is deliberate — it's a more useful signal than a checklist that claims
more than the code backs up.

---

## Tech stack

| Layer | Choice |
| :-- | :--- |
| API | FastAPI, Pydantic v2 |
| ORM / migrations | SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL (Supabase in this deployment) with automatic SQLite fallback for local dev |
| Auth | JWT (PyJWT), bcrypt password hashing (passlib) |
| Frontend | React 18, TypeScript, Vite |

---

## Project structure

```
flowforge-ai/
├── flowforge_ai/
│   ├── main.py                     # FastAPI app entrypoint + CORS
│   ├── database.py                 # Engine, session factory, SQLite fallback
│   ├── models.py                   # SQLAlchemy models (10 tables)
│   ├── config/settings.py          # Pydantic settings (env-driven)
│   ├── control_plane/
│   │   ├── auth/                   # Register, login, project CRUD, RBAC
│   │   ├── job_routes.py           # Queues, jobs, batches, cron, DLQ, diagnostics
│   │   └── worker_routes.py        # Worker registration & heartbeats
│   └── execution_plane/            # Worker coordinator, executor, reaper (in progress)
├── alembic/                        # Migrations
├── docs/                           # Requirements, architecture, API/DB design, decisions
├── tests/                          # Pytest suite
├── frontend/                       # React + Vite operator console
├── requirements.txt
└── .env                            # Local only — not committed
```

---

## Running it locally

**Backend**
```bash
pip install -r requirements.txt
```
Create a `.env` in the repo root:
```
DATABASE_URL=postgresql://postgres:YOUR-PASSWORD@db.YOUR-PROJECT-REF.supabase.co:5432/postgres
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
WORKER_HEARTBEAT_TIMEOUT_SECONDS=15
CRON_GRACE_WINDOW_MINUTES=15
```
`DATABASE_URL` can be omitted for local dev — it falls back to a SQLite file automatically.
```bash
alembic upgrade head
python -m uvicorn flowforge_ai.main:app --reload
```
API docs: http://127.0.0.1:8000/docs

**Frontend**
```bash
cd frontend
npm install
npm run dev
```
Console: http://localhost:5173

**Tests**
```bash
python -m pytest -v
```

---

## Documentation

Design rationale, the database schema, API contracts, and sequence flows are in `docs/`:
- `docs/01-project-requirements.md`
- `docs/02-system-architecture.md`
- `docs/03-module-class-layouts.md`
- `docs/04-api-contracts-and-database-design.md`
- `docs/05-sequence-flows.md`
- `docs/06-ai-architecture.md`
- `docs/07-design-decisions.md`
