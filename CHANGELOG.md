# Changelog

All notable changes to the **FlowForge AI** project will be documented in this file.

---

## [0.2.0] - 2026-08-22

### Added
- **Phase 2.6 — Technical Design Decisions & Trade-offs**:
  - Created `docs/07-design-decisions.md` specifying reasons, trade-offs, and mitigations for database choices, locking structures, subprocess isolation, static task registries, and async APIs.
- **Phase 2.5 — AI Diagnostics Architecture & Prompt Design**:
  - Created `docs/06-ai-architecture.md` specifying the asynchronous failure diagnostics workflow, failsafe isolation, prompt template, local HTTP client target hosting model, and local testing mock engine.
- **Phase 2.4 — Sequence Flows & Runtime Interaction Designs**:
  - Created `docs/05-sequence-flows.md` specifying critical runtime sequence flows using Mermaid diagrams.
  - Defined interaction sequence designs for atomic job claiming, sandbox task execution, liveness heartbeats & Reaper sweep loops, cron trigger scheduler occurrence prevention, and batch child completion.
  - Specified locking order correctness constraints and conditional fencing write rules to guarantee system isolation.
- **Phase 2.3 — API Contracts & Database Design**:
  - Created `docs/04-api-contracts-and-database-design.md` detailing the logical PostgreSQL schema, composite indices, and constraints.
  - Formulated the concurrent claiming query utilizing `SELECT FOR UPDATE SKIP LOCKED` and database-level fencing token invariants.
  - Mapped API contracts (REST routes, inputs, outputs, errors) for authentication, projects, queues, jobs, batches, crons, and DLQ.
- **Phase 2.2 — Module & Class Layouts**:
  - Created `docs/03-module-class-layouts.md` mapping logical components across Control, Execution, and AI Diagnostics planes.
  - Specified logical components (Authenticator, Authorizer, SchedulerService, BatchManager, Executor, etc.) with responsibilities, inputs/outputs, and invariants.
  - Established dependency direction rules, state ownership guidelines, and a Mermaid interaction flow diagram.
- **Phase 2.1 — System Architecture Principles**:
  - Created `docs/02-system-architecture.md` outlining the platform's architectural framework.
  - Defined 12 core architecture goals and 10 design principles.
  - Outlined the system boundary mapping UI, Control Plane (FastAPI), DB (PostgreSQL), Scheduler, Worker system, Reaper, and Observability layers.
  - Classified responsibilities and plane boundaries (Control vs. Execution).
  - Codified system correctness invariants (including batch terminal state propagation).
  - Specified technology constraints and defined failure behavior policies (including cron missed-window grace rules).
  - Explicitly defined the API/control-plane rate-limiting boundary to protect protected API operations (like job creation) while deferring concrete mechanisms and thresholds to later phases.
  - Setup architectural rules and identified deferred design decisions for future sub-phases.

---

## [0.1.2] - 2026-08-22

### Added
- **Phase 1 Final Addendum Corrections**:
  - Defined default missed window grace period (15 minutes) and policies (`RUN_ONCE`, `FORCE_RUN`, `SKIP`) for recurring jobs, including uniqueness checks to prevent duplicate execution.
  - Specified batch terminal state conditions and configurable callback trigger conditions.
  - Added a default job payload JSON size limit of 100 KB with HTTP 413 error code validation before DB insertion.
  - Added API rate-limiting requirements to the job creation endpoint (`POST /api/v1/projects/{project_id}/jobs`).

---

## [0.1.1] - 2026-08-22

### Changed
- **Requirements Revision**: Revised and strengthened the `docs/01-project-requirements.md` specifications following independent review feedback.
  - Added a detailed **Job Timeout Policy** (defaults, maximums, retry decrement, heartbeat distinction).
  - Defined the **Queue Concurrency Limit Invariant** and SQL-level atomic checks.
  - Specified a **Worker Execution Model** (Async Coordinator + Process Pool).
  - Addressed the **Heartbeat/Reaper/Retry Race Condition** using a version-controlled fencing token check.
  - Defined **Worker Failure Semantics** and returned-worker self-abortion behavior.
  - Expanded **Authorization (RBAC)** roles (Project Owner, Developer, Operator) and required strict project-level resource isolation.
  - Strengthened **Idempotency Key Semantics** (composite key uniqueness, duplicate response mapping, and retention).
  - Decoupled **AI Failure States & UI Behavior** from the core scheduling state.
  - Added **Execution Log Retention**, size limits (100KB truncation), and sensitive data masking.
  - Added 12 **Requirements-Level Test Specifications** for core failure scenarios.

---

## [0.1.0] - 2026-08-22

### Added
- **Project Structure**: Setup standard repository structure with basic configuration.
- **Git Config**: Added `.gitignore` configured for Python, Node, Vite, IDEs, and local environments.
- **Project README**: Created `README.md` defining project details, team roles, and phase plans.
- **Project Status Tracker**: Created `PROJECT_STATUS.md` to track phase checklists and open questions.
- **Requirements Specification**: Created `docs/01-project-requirements.md` covering all 40 requirements for FlowForge AI, including problem statement, target users, job scheduling types, job lifecycle state machine, distributed worker heartbeats, failsafes, and initial tech stack proposal.
