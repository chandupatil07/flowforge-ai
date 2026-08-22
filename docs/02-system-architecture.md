# FlowForge AI — System Architecture & Boundaries

This document defines the foundational system architecture, goals, component boundaries, invariants, and constraints for **FlowForge AI**. It establishes the architectural framework necessary to guide the subsequent detailed design and implementation phases, ensuring consistency, reliability, and security across the entire platform.

---

## 1. Architecture Goals
The FlowForge AI architecture is designed to satisfy the requirements established in Phase 1, prioritizing system correctness, operational visibility, and resilience. The core goals are:

- **Reliable, At-Least-Once Execution**: Guarantee that once a job is submitted and its transaction commits, it will eventually execute at least once, even in the event of worker or scheduler crashes.
- **Correct Concurrent Claiming**: Prevent race conditions where multiple workers poll simultaneously, ensuring that exactly one worker is awarded ownership of a job.
- **Horizontal Worker Scalability**: Support scaling worker instances horizontally (up or down) without requiring a central coordinator process or complex cluster managers.
- **Worker Failure Detection & Recovery**: Automatically detect worker nodes that crash, freeze, or lose network connectivity, and safely reschedule their active jobs.
- **Strict Execution Timeouts**: Monitor job execution times in isolated environments and terminate runaway tasks before they exhaust system capacity.
- **Flexible Retry & DLQ Management**: Calculate backoffs (fixed, linear, exponential) asynchronously and route permanently failing jobs to a Dead Letter Queue (DLQ) for analysis and replay.
- **Fencing-Token Correctness**: Prevent late, stale, or partitioned workers from writing job success/failure updates to the database after the system has recovered and reassigned their jobs.
- **Idempotent Job Submission**: Guard the API from duplicate job creation requests using project-scoped idempotency keys.
- **Strict Multi-Project Isolation**: Enforce security boundaries that prevent any cross-tenant leakage of jobs, queues, configurations, or logs.
- **High Observability**: Centralize operational metrics (throughput, depths, worker load) and execution logs for ease of support.
- **Decoupled AI Diagnostics**: Ensure the core scheduler and execution layers operate normally even if the AI failure analysis model is completely offline or slow.
- **Separation of Control and Execution Planes**: Isolate the business logic of scheduling and monitoring (control) from the arbitrary execution of job code (execution).

---

## 2. Architecture Principles
The design of FlowForge AI must adhere to the following architectural guidelines:

- **Principle 1 — PostgreSQL is the Single Source of Truth**: The relational database is the authoritative state store for job states, queues, worker registries, and configurations. No external brokers (Redis, RabbitMQ, Kafka) or distributed memory caches may be introduced as the state authority.
- **Principle 2 — Correctness before Throughput**: Distributed correctness (preventing duplicate execution, enforcing concurrency limits, respecting project isolation) takes absolute precedence over premature optimization or throughput maximization.
- **Principle 3 — Atomic Claiming**: Job claiming must be treated as a single atomic operation at the database level. No intermediate states (e.g. "claiming in progress") are permitted to exist in-memory outside the database transaction scope.
- **Principle 4 — Fencing Tokens**: State modifications on job rows must require a valid fencing/ownership token to prevent writes from stale/lagged workers.
- **Principle 5 — AI is not in the Critical Path**: AI failure diagnostics are non-blocking, asynchronous add-ons. The core engine must execute, schedule, retry, and manage jobs normally regardless of AI availability.
- **Principle 6 — Design for Failure**: Schedulers, APIs, workers, and network links will fail. The system must automatically recover from components going offline without manual intervention.
- **Principle 7 — Clear Responsibility Boundaries**: Each component has a single, non-overlapping responsibility. No two components should manage or mutate the same system states simultaneously.
- **Principle 8 — Observable Operations**: Every critical state transition, worker registration, heartbeat, and execution exception must produce structured traces/logs.
- **Principle 9 — Security by Boundary**: Authentication, RBAC checks, rate limits, and payload validation must be enforced at the outermost entrance to the control plane.
- **Principle 10 — Prefer Simple Infrastructure for MVP**: Minimize third-party dependencies to keep local development, testing, and Docker deployment simple, reliable, and self-contained.

---

## 3. System Boundary
The system boundaries of FlowForge AI are defined as follows:

```
FlowForge-AI System Boundary
├── [Client Web Browser / CLI] (External)
│     │
│     ▼
├── Web UI (React Single Page Application)
│     │ (REST API via HTTPS / JSON)
│     ▼
├── API / Control Plane (FastAPI Gateway)
│     ├── Authentication / Authorization (JWT / RBAC)
│     ├── Input Validation & Payload Size Checks
│     └── Rate Limiter
│           │
│           ├── (Reads/Writes persistent state)
│           ▼
├── PostgreSQL Database (Authoritative Job & Registry Store)
│     │
│     ├── (Polled by Schedulers)
│     ├─► Scheduler (Cron Evaluation & Delay Rescheduler)
│     │
│     ├── (Polled by Workers)
│     ├─► Worker System (Async Coordinators & Process-based Job Execution)
│     │
│     ├── (Polled by Reaper)
│     ├─► Failure Recovery / Reaper (Liveness Monitor & Log Pruner)
│     │
│     └── (Triggered on failures)
└── AI Analysis Service (Local LLM / Diagnostic Engine - Decoupled)
```

---

## 4. Major Component Responsibilities

| Component | Responsibility | Must NOT own / do |
| :--- | :--- | :--- |
| **Web UI** | Renders dashboard; displays metrics, logs, queues, and worker health; initiates manual retries and triggers AI diagnostics. | Must not execute jobs; must not directly write to the database; must not maintain authoritative state. |
| **FastAPI / API** | Enforces authentication/JWT; performs RBAC permission checks; validates payload sizes; rate-limits routes; writes new jobs to DB. | Must not block on job execution; must not handle worker process execution; must not poll jobs. |
| **PostgreSQL** | Stores persistent states of projects, users, queues, jobs, heartbeats, execution logs; enforces atomic row locks. | Must not evaluate cron timers; must not coordinate worker process pools; must not execute user job scripts. |
| **Scheduler** | Evaluates recurring cron rules; updates delayed jobs whose `scheduled_for` is ripe; manages batch terminal callbacks. | Must not execute job code; must not manage worker process pools; must not claim jobs for workers. |
| **Worker** | Runs the Async Coordinator (polls DB, registers worker, sends heartbeats); dispatches jobs to isolated child processes. | Must not perform global scheduling; must not recover other workers; must not allow stale updates. |
| **Reaper** | Runs periodically; checks worker heartbeat ages; marks dead workers `OFFLINE`; recovers orphaned jobs; prunes expired logs. | Must not execute normal jobs; must not process user API requests. |
| **AI Engine** | Parses error logs and stack traces; generates failure summaries, root causes, and suggest remediations. | Must not modify job execution state; must not decide retry outcomes; must not block execution loops. |
| **Observability** | Exposes metrics endpoints; collects throughput, queue depths, latencies, and worker loads. | Must not maintain the source-of-truth job states; must not lock database resources. |

---

## 5. Control Plane vs. Execution Plane
The architecture strictly decouples the control operations from task execution:

### 5.1 Control Plane
- **Scope**: Includes API gateways, authentication/authorization services, database locking, queue priority routing, cron scheduling calculations, reaper failover, and DLQ routing.
- **Primary Objective**: Maintain the integrity, consistency, and security of the global system state.

### 5.2 Execution Plane
- **Scope**: Includes the worker Async Coordinators, child processes executing custom Python task code, standard output/error capturing, and local process timeout monitors.
- **Primary Objective**: Execute user-defined task payloads concurrently and report execution output.

### 5.3 Architectural Separation Rationale
- **Fault Containment**: Crashing or freezing task code (e.g., infinite loop, C-level segfault, memory leak) only terminates that specific child execution process. The worker coordinator and global control plane remain online and responsive.
- **Resource Protection**: Ensures that execution-level resource spikes do not starve the API gateway or database connection pools of processing capacity.

---

## 6. Core Architectural Invariants
The system design must preserve the following correctness invariants:

1. **Single Job Ownership**: A job record can have at most one active worker owner at any point in time. The `worker_id` and `status = 'RUNNING'` or `'CLAIMED'` must map 1:1.
2. **Fencing Token Write-Locking**: Any status update to a job (`COMPLETED`, `FAILED`) must conditionally match the current `ownership_token` in the database. Stale workers whose ownership has been revoked by the reaper must affect 0 rows and abort.
3. **Strict Queue Concurrency Limits**: The number of concurrently executing jobs in Queue X must never exceed Queue X's concurrency limit $N$. Concurrency counts must be evaluated atomically during the claiming transaction.
4. **Reliable State Persistence**: Job state transitions must commit to PostgreSQL before any external execution actions or changes are visible to workers.
5. **AI Subsystem Decoupling**: If the AI diagnostics engine is disabled or fails, workers must execute, log, retry, and route jobs to the DLQ normally.
6. **Project Scope Isolation**: A user or worker request can only query, create, or modify database records (jobs, queues, logs) that explicitly match their authorized `project_id`.
7. **Cron Execution Uniqueness**: A single scheduled occurrence of a cron configuration `(cron_config_id, scheduled_for)` can be queued at most once, preventing duplicate execution due to scheduler restarts.
8. **Idempotency Scoping**: Submitting two job creation requests with identical `(project_id, idempotency_key)` must result in a single database job record.
9. **Batch State and Callback Propagation**:
   - A batch becomes terminal if and only if all of its child jobs are in terminal states (`COMPLETED` or `DLQ`).
   - If all child jobs are successfully completed (`COMPLETED`), the batch state resolves to `SUCCESS`.
   - If at least one child job permanently fails (ends in `DLQ`), the batch state resolves to `FAILED`.
   - The batch callback must fire only when the batch achieves a terminal state, and its execution trigger must adhere strictly to the configured `callback_trigger_condition` (`ALWAYS`, `ON_SUCCESS`, `ON_FAILURE`, `NEVER`).

---

## 7. Technology Boundaries
The FlowForge AI architecture is constrained to the following technology stack:

- **Frontend**: React SPA, Vite, Axios, Tailwind CSS, Recharts.
- **Backend / API**: Python 3.11+, FastAPI, Pydantic v2.
- **Database**: PostgreSQL 15+, SQLAlchemy 2.0 (asyncpg driver), Alembic migrations.
- **Worker Concurrency**: Asyncio coordinator process managing isolated subprocesses / process pools.
- **AI Diagnostics**: Local Python-based LLM integration (Hugging Face pipelines, Ollama API, or a mock utility fallback).
- **Deployment**: Docker, Docker Compose.

*Prohibited Components (unless explicitly approved later)*: Redis, Kafka, RabbitMQ, Celery, Kubernetes, cloud-proprietary databases/APIs.

---

## 8. Data Ownership Principle
PostgreSQL is the sole persistent authority.
- **No In-Memory Authority**: Workers do not hold authoritative in-memory lists of jobs. If a worker process restarts, its list is rebuilt entirely by querying the database.
- **No Cache Authority**: The Web UI and API gateways are stateless; they query the database dynamically for metrics, statuses, and logs.
- **AI Isolated Read-Only**: The AI diagnostics engine reads logs and payload arguments from the database but cannot modify scheduler tables or job lifecycle records.

---

## 9. Failure Architecture Principles
The system must handle component failures gracefully according to these behaviors:

- **API Gateway Crashes**: FastAPI nodes are stateless. If one crashes, incoming traffic is routed to other nodes. DB transactions commit or roll back cleanly.
- **Scheduler Process Crashes (Missed Cron Recovery)**:
  - The scheduler runs periodically. If it crashes or is offline, missed recurring cron executions are caught up upon restart according to the configured policies:
    - **Default Policy (RUN_ONCE)**: Missed executions are evaluated against a **15-minute grace period** from the scheduled time. If recovery occurs within 15 minutes of the trigger, the scheduler generates exactly one catch-up execution. If recovery occurs after 15 minutes, the missed execution is skipped.
    - **FORCE_RUN**: Always generates exactly one catch-up execution upon recovery, regardless of the missed run's age.
    - **SKIP**: Discards all missed runs during downtime and schedules only the next upcoming cron trigger.
  - To prevent duplicate queuing of the same trigger during scheduler crash recovery or concurrent execution instances, the scheduled occurrence rule (`(cron_config_id, scheduled_for)` unique constraint) must prevent duplicate queueing of the same cron occurrence.
- **Worker Coordinator Crash**: The worker ceases to write heartbeats. Within 15 seconds, the Reaper identifies the worker as dead, marks it `OFFLINE`, and safely re-queues its active jobs.
- **Worker Heartbeat Loss (Network Partition)**: If a worker loses database connectivity but remains active, the reaper marks its jobs `QUEUED`. When the worker recovers and attempts to complete the job, the fencing token rejects the write, and the worker aborts.
- **Reaper Failure**: If the reaper goes offline, dead workers are not detected. When the reaper is restarted, it scans all heartbeats historically and recovers all accumulated orphans.
- **AI Subsystem Failure**: If the LLM engine crashes or times out, the job fails/retries normally. The AI analysis status is marked `FAILED` or `UNAVAILABLE` in the database, and the operator is notified on the UI.
- **Database Failure**: The entire platform enters read-only or offline mode. Workers stop polling and enter exponential backoff waiting for DB recovery.

---

## 10. Security Boundaries
The architecture enforces security at defined filters:

```
[External Client Request]
       │ (Enforces HTTPS)
       ▼
[FastAPI Router Gateway]
       │ (Enforces JWT Signature Validation & Expiry)
       ▼
[Role-Based Access Checks (RBAC)]
       │ (Ensures Project Owner vs. Developer vs. Operator permissions)
       ▼
[Project Isolation Boundaries]
       │ (Enforces WHERE project_id = client_authorized_project_id)
       ▼
[Payload Validation Filters]
       │ (Enforces Pydantic schema validation & 100 KB payload size limit)
       ▼
[Database Transaction / Query Engine]
```

### 10.1 Rate Limiting at the Boundary
- **Enforcement Layer**: Rate limiting is enforced at the API/control-plane boundary for protected API operations (including authentication, token requests, and job creation routes such as `POST /api/v1/projects/{project_id}/jobs`).
- **Objective**: Protect database resources, CPU performance, and downstream workers from excessive request rates, denial-of-service (DoS) attempts, or buggy loop submissions.
- **Implementation Independence**: The architecture preserves the rate-limiting requirements defined in Phase 1 while leaving the concrete enforcement mechanisms (e.g. middleware, rate-limit buckets) and exact limit values to subsequent detailed architecture and implementation phases.

---

## 11. Scalability Principles
- **Stateless API Gateway**: Scale the API horizontally by deploying multiple FastAPI containers behind a load balancer.
- **Horizontally Scalable Workers**: Start any number of worker containers on different hosts. They coordinate independently by running atomic DB queries using `SKIP LOCKED`.
- **Stateless Schedulers**: Schedulers do not maintain local queues; they execute periodic synchronization queries against PostgreSQL.
- **Database Scale Limitations**: Because PostgreSQL is the central coordinator, database CPU and lock contention are the primary scalability limiters. This is mitigated by using fast indexes, short transaction scopes, and polling backoffs when queues are empty.

---

## 12. Observability Boundary
The system architecture must expose raw operational data for visibility:
- **Metrics (JSON Exporter)**: Queue depths, active worker loads, success/failure throughput rates, job run times, and queue latency.
- **Application Traces**: Structured, JSON-formatted stdout logs from FastAPI, Schedulers, and Worker Coordinators.
- **Job Execution Logs**: Full stdout/stderr streams from child processes executing tasks, stored in PostgreSQL with a 100KB limit and credential masking.

---

## 13. Architecture Decision Rules
To guide future technical design choices, developers must follow these rules:

1. **Simplicity First**: Implement the simplest design that satisfies the correctness guarantees. Do not write complex code to solve performance problems that do not yet exist.
2. **Infrastructure Minimalist**: Do not introduce databases, message queues, caches, or third-party binaries without review and approval.
3. **Database Consistency Over Performance**: Never optimize a query or remove a row lock if it risks double execution or state corruption.
4. **Asynchronous Non-Critical Path**: Always isolate non-critical features (like AI diagnostics or log cleaning) from the core database claiming and execution loops.
5. **Platform Independence**: Ensure all architecture concepts (such as process isolation and timeouts) are designed to run cleanly in both local Windows dev systems and Linux production containers.

---

## 14. Explicit Non-Goals for Phase 2.1
This document does **not** define or implement:
- The exact SQL tables, primary/foreign keys, or migrations (handled in Phase 3).
- Python file directories, import pathways, or package structure (handled in Phase 2.2).
- The exact API paths, parameters, or JSON bodies (handled in Phase 2.3).
- The specific AI model file, provider, or prompt template (handled in Phase 9).
- Docker Compose files or network configs (handled in Phase 10).

---

## 15. Open Architectural Decisions
The following decisions are intentionally deferred and will be resolved in later tasks:

1. **State-Transition Model**: The specific workflow status strings and transitional validation logic.
2. **Atomic Claim Query**: The exact SQL syntax for joining queues, counting concurrency, and locking rows.
3. **Cron Parser Library**: The specific library used to evaluate cron triggers (e.g. `croniter`).
4. **Worker Process Pool Strategy**: The exact Python multiprocessing library or subprocess method used to spawn job executions on different operating systems.
5. **Heartbeat & Reaper Timers**: Tuning the default interval and offline threshold values based on performance tests.
6. **Token/JWT Secret Management**: Choosing how environment secrets are loaded (e.g. env variables, dotenv files).
7. **AI Model Hosting**: Decoupling LLM calls via a separate microservice, a local subprocess, or an external free API wrapper.
8. **Logging Storage**: Determining if execution logs are stored directly in PostgreSQL or written to an external volume and referenced in SQL.
