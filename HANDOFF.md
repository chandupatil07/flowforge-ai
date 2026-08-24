# FlowForge AI — Builder Handoff Document

This file tracks what each AI agent (Antigravity/Claude) has done and what remains.
Claude or the next agent should read this file FIRST before doing any work.

---

## Last Updated By: Antigravity (2026-08-24)

## Current State: STAGE 2 — IN PROGRESS

---

## COMPLETED WORK

### Phase 1 — Requirements (LOCKED)
- `docs/01-project-requirements.md` — 40-point requirements spec, fully reviewed and approved.

### Phase 2 — Architecture Design (LOCKED)
- `docs/02-system-architecture.md` — System boundaries, control/execution plane separation.
- `docs/03-module-class-layouts.md` — Module layouts, dependency vectors, component interactions.
- `docs/04-api-contracts-and-database-design.md` — PostgreSQL schema, atomic claiming CTE, REST endpoints.
- `docs/05-sequence-flows.md` — Mermaid sequence diagrams for all critical flows.
- `docs/06-ai-architecture.md` — AI diagnostics workflow, prompt template, failsafe design.
- `docs/07-design-decisions.md` — Tech justifications, locking strategy, subprocess isolation.

### Stage 1 — Database + Backend Foundation (COMPLETED)
Files created/modified:
- `flowforge_ai/config/settings.py` — Pydantic settings with env var loading.
- `flowforge_ai/database.py` — SQLAlchemy engine, SessionLocal, get_db dependency.
- `flowforge_ai/models.py` — All 10 SQLAlchemy models with composite FKs, checks, indices.
- `flowforge_ai/main.py` — FastAPI app entrypoint.
- `flowforge_ai/control_plane/auth/auth_service.py` — Password hashing, JWT, RoleChecker.
- `flowforge_ai/control_plane/auth/routes.py` — Register, login, project CRUD endpoints.
- `alembic/` — Alembic migrations config and initial schema migration.
- `tests/test_stage1.py` — Auth + RBAC isolation tests (ALL PASSING).

### Key Technical Decisions Already Made:
- SQLite fallback for local dev/testing (no psycopg2 installed).
- UUID stored as String(36) for cross-DB compatibility.
- `foreign()` annotation needed on `AIDiagnostics.project_id` relationship.
- Cyclical FK between `batches` and `jobs` handled via conditional post-alter.
- bcrypt for password hashing, PyJWT for token signing (HS256).

---

## REMAINING WORK

### Stage 2 — Core Job Engine
- [ ] Queue CRUD endpoints (create, list, get)
- [ ] Job submission endpoint with payload validation (100KB limit)
- [ ] Idempotency key handling (unique constraint conflict → return existing job)
- [ ] Job status query endpoints
- [ ] Job cancellation endpoint
- [ ] Cron config CRUD endpoints
- [ ] Batch creation endpoint
- [ ] Static task handler registry
- [ ] Worker registration endpoint

### Stage 3 — Reliability
- [ ] Worker coordinator polling loop (asyncio)
- [ ] Atomic job claiming (deterministic queue lock → eligible job → CLAIMED)
- [ ] Executor subprocess isolation
- [ ] Timeout monitoring and forceful termination
- [ ] Log capture, sanitization (mask secrets), truncation (100KB)
- [ ] Fencing token verification on job completion writes
- [ ] Reaper daemon (heartbeat timeout → OFFLINE → reclaim/DLQ)
- [ ] Cron scheduler (next occurrence calculation, grace windows, missed run policies)
- [ ] Batch completion monitor and callback trigger

### Stage 4 — AI Diagnostics
- [ ] DiagnosticStateManager (triggered on FAILED/DLQ)
- [ ] AIDiagnosticsEngine (async httpx client to Ollama/OpenAI-compatible API)
- [ ] Prompt template injection and JSON response parsing
- [ ] MockAIDiagnosticsEngine for testing
- [ ] Failsafe timeout (5s default) and fallback messages

### Stage 5 — Frontend + Testing + Deployment
- [ ] React/Vite dashboard
- [ ] Integration tests (multi-worker concurrent claims)
- [ ] Docker Compose configuration

---

## IMPORTANT NOTES FOR NEXT AGENT
1. All tests must pass before committing: `python -m pytest`
2. Do NOT push to GitHub.
3. Do NOT modify docs/01 through docs/07 unless there's a real implementation blocker.
4. PostgreSQL 17 is installed and running locally but no psycopg2 driver exists.
5. The project uses SQLite fallback (`flowforge.db`) for local dev.
6. `__init__.py` files are NOT created — Python finds modules via path manipulation.
7. Pydantic V2 is installed — use `model_config = ConfigDict(...)` not `class Config`.
8. FastAPI version installed is 0.111+ (starlette 0.37).
