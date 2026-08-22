# FlowForge AI — Intelligent Distributed Job Orchestration & Reliability Platform

FlowForge AI is a production-inspired, highly reliable distributed job scheduling and orchestration platform designed to handle background execution of immediate, delayed, scheduled, cron, and batch jobs. It leverages a SQL-native architecture (using Python, FastAPI, SQLAlchemy, and PostgreSQL) to offer strict database transactional guarantees, multi-tenant project separation, worker liveness monitoring, and intelligent AI-powered job failure diagnostics.

---

## Key Features
1. **Strict Transactional Boundaries**: Avoid the dual-write problem by queueing jobs in the same transaction as your business logic.
2. **Atomic Job Claiming**: Database-level concurrency control (`FOR UPDATE SKIP LOCKED`) ensures that no two workers execute the same job.
3. **Flexible Scheduling**: Supports immediate execution, specific delays, future timestamps, cron-like recurring jobs, and aggregate progress-tracked batches.
4. **Worker Liveness & Auto-Recovery**: Heartbeat-based monitoring automatically detects dead workers and safely re-queues orphaned/running jobs.
5. **AI-Powered Diagnostics**: Non-blocking failure summaries, root cause analyses, and suggested fixes powered by local AI execution.
6. **Granular Queue Controls**: Control priorities, dynamic pause/resume, and global concurrency limits per queue.
7. **Dead Letter Queue (DLQ)**: Handles permanently failed jobs with full logs and manual replay capability.
8. **Interactive Dashboard**: Full observability dashboard built with React and Vite for job tracking, logs, and system metrics.

---

## Repository & Team Roles

- **Repository URL**: [https://github.com/chandupatil07/flowforge-ai](https://github.com/chandupatil07/flowforge-ai)
- **Team**:
  1. **Project Owner / Student**
  2. **ChatGPT**: Project architect, coordinator, requirement reviewer, phase planner, and interview mentor.
  3. **Antigravity** (You): **PRIMARY IMPLEMENTATION AGENT** (Local execution and pair-programming assistant).
  4. **Claude**: Independent senior technical reviewer and secondary implementation assistant.

---

## Phase Plan & Status
We are building this project one phase at a time to ensure high engineering quality, consistency, and alignment.

*   **PHASE 0: Project understanding** (Completed)
*   **PHASE 1: Requirements & System Analysis** (Current Phase - Completed Documentation Foundation)
*   **PHASE 2: System Architecture** (Not Started)
*   **PHASE 3: Database Design** (Not Started)
*   **PHASE 4: Backend Foundation** (Not Started)
*   **PHASE 5: Job Scheduling Engine** (Not Started)
*   **PHASE 6: Distributed Worker System** (Not Started)
*   **PHASE 7: Reliability & Concurrency** (Not Started)
*   **PHASE 8: Advanced/Bonus Features** (Not Started)
*   **PHASE 9: AI Failure Analysis** (Not Started)
*   **PHASE 10: Frontend Dashboard** (Not Started)
*   **PHASE 11: Testing** (Not Started)
*   **PHASE 12: Production Hardening** (Not Started)
*   **PHASE 13: Documentation** (Not Started)
*   **PHASE 14: Final Review & Submission** (Not Started)
*   **PHASE 15: Interview Revision** (Not Started)

For details on current progress, files modified, and verification steps, refer to [PROJECT_STATUS.md](file:///c:/Users/balaj/OneDrive/Desktop/flowforge-ai/PROJECT_STATUS.md).

---

## Project Setup & Documentation
Documentation is situated in the `docs/` folder:
- [01-project-requirements.md](file:///c:/Users/balaj/OneDrive/Desktop/flowforge-ai/docs/01-project-requirements.md) (Current phase detailed requirements spec).

*Note: Code base setup and development will start in subsequent phases upon requirement review and approval.*
