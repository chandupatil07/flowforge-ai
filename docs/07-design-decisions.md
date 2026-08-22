# FlowForge AI — Technical Design Decisions & Trade-offs

This document details the core technical design decisions, trade-offs, and architectural justifications for **FlowForge AI**. It documents why specific technology paths were chosen and how they satisfy the platform's reliability, consistency, and performance requirements.

---

## 1. Purpose
During the requirements and architecture design phases, several fundamental choices were made regarding state persistence, task execution, isolation, and concurrency control. This document serves as the permanent record of those justifications, providing the engineering context for future maintainers.

---

## 2. Core Design Justifications

### 2.1 Persisted State: PostgreSQL-Native vs. Redis/RabbitMQ/Celery
A primary architectural constraint of FlowForge AI is its exclusive reliance on PostgreSQL as the authoritative job store, completely bypassing Redis, RabbitMQ, Celery, or similar message brokers.

#### Rationale & Advantages
- **Transactional Consistency (The Dual-Write Problem)**: In traditional Celery/Redis setups, queueing a job requires a separate network call to Redis. If the transaction writing business data to PostgreSQL succeeds but the write to Redis fails, the job is lost. Conversely, if Redis succeeds but the DB rolls back, a ghost job executes. By saving jobs directly in the PostgreSQL database inside the same transaction block as business data, transactional consistency is guaranteed out-of-the-box.
- **Atomic Concurrency Control**: PostgreSQL allows complex conditional queries and row-level locks (e.g., `SELECT FOR UPDATE SKIP LOCKED` combined with queue checks) within a transaction, which is complex or impossible to run atomically in simple Redis key-value stores.
- **Operational Simplicity**: Bypassing external message brokers reduces infrastructure footprints, simplifies backups, and leverages PostgreSQL's proven transactional durability.

#### Trade-offs & Mitigations
- **Polling Latency & DB Load**: Frequent polling from concurrent worker nodes can cause database CPU spikes.
  - *Mitigation*: We utilize index-optimized queries (`idx_jobs_claim_polling`) and implement exponential poll backoffs (e.g. sleep intervals between 0.5s and 5.0s when queues are empty) to limit idle query rates.

---

### 2.2 Claiming Strategy: Per-Queue Lock Serialization vs. Optimistic Locks
To enforce the queue-level concurrency limit $N$, claims must lock database resources atomically to avoid race conditions.

#### Rationale & Advantages
- **Pessimistic Concurrency Locking**: The claiming query locks candidate queues deterministic-wise (`ORDER BY q.id FOR UPDATE`) before calculating active count and selecting jobs. This guarantees that concurrent workers polling the same queue are serialized at the query entry point, preventing race conditions where multiple workers observe the same capacity slot and exceed $N$.
- **SKIP LOCKED Efficiency**: Individual job rows are locked using `FOR UPDATE OF j SKIP LOCKED`. This allows parallel workers polling *different* queues or looking for different job classes to bypass locked records instantly, preserving high performance.

#### Trade-offs & Mitigations
- **Queue Lock Bottleneck**: Serializing claims on queue headers locks the queue for the duration of the transaction.
  - *Mitigation*: Keep the claim transaction extremely short. The transaction locks the queue, updates the job status to `CLAIMED` (writing the worker ID and token), and immediately commits, releasing the lock in milliseconds before the job is actually executed.

---

### 2.3 Worker execution: Async Coordinator + Process Pool vs. Thread Pools
The worker agent uses a hybrid model: an asynchronous asyncio loop for coordination and polling, combined with spawning isolated process contexts for job execution.

#### Rationale & Advantages
- **GIL Bypass**: Python's Global Interpreter Lock (GIL) prevents threads from running CPU-bound tasks concurrently. Spawning isolated process contexts allows multi-core CPU capacity utilization.
- **Memory Leakage and Crash Defense**: User-defined task handlers can contain memory leaks or throw unhandled system exceptions (e.g., segment faults). Running tasks in isolated processes insulates the worker coordinator, ensuring worker liveness.
- **Forceful Termination**: If a job exceeds its configured timeout threshold, process context isolation allows the coordinator to send a SIGKILL signal directly to the child process, immediately releasing system resources. This is impossible to execute safely with standard Python threads.

#### Trade-offs & Mitigations
- **Process Spawning Overhead**: Spawning processes is more expensive than spawning threads.
  - *Mitigation*: The worker coordinator maintains a pool of process slots matching its configured capacity limit, recycling process contexts where appropriate or capping max concurrent runs.

---

### 2.4 Task Registration: Static Registry vs. Dynamic Importing
The platform must map incoming `target_handler` strings to executable Python functions. We evaluated two models:

```
[Static Registry Approach]
   - Developer explicitly registers functions in a central config file.
   - High security, predictable memory footprint.
   - Slightly more boilerplate code.

[Dynamic Importing Approach]
   - System dynamically imports modules at runtime (e.g. importlib.import_module).
   - Zero boilerplate code.
   - Security risk (arbitrary code execution) and import side-effects.
```

#### Final Decision & Rationale
We chose the **Static Task Registry** approach.
- **Security Boundaries**: Dynamic importing allows execution of arbitrary Python modules if a tenant payload gets corrupted. A static registry acts as an explicit allow-list, preventing unauthorized module execution.
- **Predictable Imports**: Avoids runtime circular import crashes, resource leaks, or slow first-run imports during active execution.

---

### 2.5 AI Diagnostics: Decoupled client vs. Local ML Frameworks
AI-powered diagnostics are decoupled through standard OpenAI-compatible HTTP requests rather than executing ML models locally inside the worker context.

#### Rationale & Advantages
- **Lightweight Worker Footprint**: Executing Llama/Mistral models locally requires heavy framework installations (PyTorch, CUDA) and high VRAM/GPU availability. Decoupling ensures workers remain lightweight and deployable on cheap, generic CPU compute.
- **Decoupled Failure Isolation**: The HTTP client wrapper ensures that any LLM host crash, network latency spike, or token limit error fails silently, writing fallback messages to the database without impacting scheduling.

---

## 3. Tech Stack Decisions Summary

| Component | Technology Selected | Rationale |
| :--- | :--- | :--- |
| **Database** | **PostgreSQL** | Authoritative ACID store, native locks, SKIP LOCKED support. |
| **Backend API** | **FastAPI + Asyncio** | High performance, lightweight, built-in background tasks, easy integration. |
| **Worker Runner** | **Async Coordinator + Subprocesses** | GIL bypass, crash isolation, clean process termination. |
| **Authentication** | **Stateless JWT (HS256)** | Low validation latency, scales horizontally, simplifies authorization checks. |
| **AI Client** | **Asynchronous httpx** | Lightweight, OpenAI-compatible JSON REST api communication, mockable. |
