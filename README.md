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



## Project Setup & Documentation
Documentation is situated in the `docs/` folder:
- [01-project-requirements.md](file:///c:/Users/balaj/OneDrive/Desktop/flowforge-ai/docs/01-project-requirements.md) (Current phase detailed requirements spec).

*Note: Code base setup and development will start in subsequent phases upon requirement review and approval.*
