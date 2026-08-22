# Changelog

All notable changes to the **FlowForge AI** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
