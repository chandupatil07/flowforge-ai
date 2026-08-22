# FlowForge AI — Sequence Flows & Interaction Designs

This document defines the core runtime execution flows and sequence designs for **FlowForge AI**. It specifies how the logical modules and database layers interact to execute tasks, enforce concurrency limits, handle failures, and guarantee transaction correctness.

---

## 1. Purpose
This design document maps out the specific runtime sequences for critical platform operations. By tracing the exact step-by-step messaging, locking, and status updates, we ensure that:
- Race conditions are eliminated in concurrent schedulers and worker claims.
- Concurrency limits are strictly enforced at the database level.
- Stale workers are prevented from writing invalid results using versioned fencing tokens.
- Deadlocks are mitigated during multi-queue claiming.

---

## 2. Sequence Designs

### 2.1 Job Claiming & Queue Concurrency Locking Flow
This flow tracks how a worker coordinator claims the next available job while dynamically checking queue concurrency limits.

```mermaid
sequenceDiagram
    autonumber
    participant W as WorkerCoordinator
    participant C as Claimer
    participant DB as PostgreSQL DB

    W->>C: poll_next_job(worker_id)
    activate C
    C->>DB: Begin Transaction

    Note over C,DB: Step 1: Lock candidate queues in deterministic order by q.id to prevent deadlocks
    C->>DB: SELECT q.id, q.concurrency_limit FROM queues WHERE id IN (pending_queues) ORDER BY q.id FOR UPDATE

    Note over C,DB: Step 2: Compute active jobs (CLAIMED + RUNNING) and select eligible job
    C->>DB: WITH active_counts AS (SELECT queue_id, COUNT(*)... WHERE status IN ('CLAIMED', 'RUNNING')) SELECT j.id FROM jobs j JOIN queues q... WHERE j.status = 'QUEUED' AND COALESCE(ac.active_count, 0) < q.concurrency_limit ORDER BY j.priority DESC, j.created_at ASC LIMIT 1 FOR UPDATE OF j SKIP LOCKED

    alt Eligible Job Found
        Note over C,DB: Step 3: Atomic status transition and fencing token write
        C->>DB: UPDATE jobs SET status = 'CLAIMED', worker_id = :worker_id, ownership_token = :ownership_token, claimed_at = NOW() WHERE id = eligible_job.id
        C->>DB: Commit Transaction
        DB-->>C: Return Job record & ownership_token
        C-->>W: Return Claimed Job
    else No Eligible Job
        C->>DB: Commit / Rollback Transaction
        C-->>W: Return Null
    end
    deactivate C
```

---

### 2.2 Worker Job Execution & Sandbox Isolation Flow
This flow details how the worker coordinator delegates execution to the executor process context, captures/sanitizes streams, and writes back results with fencing checks.

```mermaid
sequenceDiagram
    autonumber
    participant W as WorkerCoordinator
    participant EX as Executor
    participant SUB as Task Subprocess
    participant L as ExecutionLogger
    participant DB as PostgreSQL DB

    W->>EX: execute_job(job_record, ownership_token)
    activate EX
    EX->>SUB: Spawn Subprocess (Isolated Process Context)
    activate SUB

    par Stream Capture & Sanitization
        SUB->>L: Stream stdout / stderr
        L->>L: Mask credentials & truncate to 100 KB
    and Timeout Monitor
        EX->>EX: Run Timeout Timer
        alt Execution Exceeds Timeout
            EX->>SUB: Force Terminate (SIGKILL / equivalent)
            SUB-->>EX: Terminated (Exit Code / Signal)
        end
    end

    SUB-->>EX: Process Exit Code (0 = SUCCESS, non-zero = FAILURE)
    deactivate SUB

    EX->>DB: Begin Transaction

    Note over EX,DB: Fencing Token Check: Verify ownership_token matches active record
    alt Job Succeeded (Exit Code 0)
        EX->>DB: UPDATE jobs SET status = 'COMPLETED', finished_at = NOW() WHERE id = job_id AND ownership_token = token
    else Job Failed or Timed Out (Exit Code non-zero)
        EX->>DB: UPDATE jobs SET status = CASE WHEN retries_remaining > 0 THEN 'QUEUED' ELSE 'DLQ' END, retries_remaining = CASE WHEN retries_remaining > 0 THEN retries_remaining - 1 ELSE 0 END, worker_id = NULL, ownership_token = NULL, finished_at = CASE WHEN retries_remaining = 0 THEN NOW() ELSE NULL END WHERE id = job_id AND ownership_token = token
    end

    alt Fencing Check Fails (0 rows affected / Claim revoked by Reaper)
        DB-->>EX: 0 rows updated
        EX->>DB: Rollback Transaction
        EX-->>W: Self-Abort Execution & Cleanup Local Footprints
    else Fencing Check Succeeds (1 row affected)
        EX->>DB: INSERT INTO job_logs (job_id, content) VALUES (job_id, sanitized_logs)
        EX->>DB: Commit Transaction
        EX-->>W: Execution finished & logged (PostgreSQL authoritative state updated)
    end
    deactivate EX
```

---

### 2.3 Worker Liveness & Reaper Orphan Recovery Flow
This flow shows the heartbeat mechanism emitted by workers and the periodic reclaim sweeps executed by the Reaper daemon.

```mermaid
sequenceDiagram
    autonumber
    participant W as WorkerCoordinator
    participant R as Reaper Daemon
    participant DB as PostgreSQL DB

    loop Heartbeat Loop (Every 5 seconds)
        W->>DB: UPDATE workers SET last_heartbeat_at = NOW() WHERE id = worker_id
    end

    loop Reaper Sweep Loop (Periodic timer tick)
        R->>DB: Begin Transaction
        Note over R,DB: Step 1: Detect heartbeat timeout (Configurable Design Default: 15s)
        R->>DB: UPDATE workers SET status = 'OFFLINE' WHERE last_heartbeat_at < NOW() - INTERVAL '15 seconds' AND status = 'ACTIVE'

        Note over R,DB: Step 2: Reclaim CLAIMED/RUNNING jobs from offline workers
        R->>DB: SELECT id, retries_remaining FROM jobs WHERE status IN ('CLAIMED', 'RUNNING') AND worker_id IN (SELECT id FROM workers WHERE status = 'OFFLINE')

        alt Retries Remaining > 0
            R->>DB: UPDATE jobs SET status = 'QUEUED', retries_remaining = retries_remaining - 1, worker_id = NULL, ownership_token = NULL WHERE id = job_id
        else Retries Exhausted (Retries Remaining = 0)
            R->>DB: UPDATE jobs SET status = 'DLQ', worker_id = NULL, ownership_token = NULL, finished_at = NOW() WHERE id = job_id
        end

        R->>DB: Commit Transaction
        Note over R: Fencing-token revoked: Stale workers will fail fencing check
    end
```

---

### 2.4 Cron/Scheduler Occurrence Prevention Flow
This flow outlines how the Scheduler daemon calculates scheduled times, applies missed run grace window rules, and prevents duplicate occurrence queuing.

```mermaid
sequenceDiagram
    autonumber
    participant S as SchedulerService
    participant DB as PostgreSQL DB

    loop Scheduler Loop (Periodic evaluation tick)
        S->>DB: Begin Transaction
        S->>DB: SELECT * FROM cron_configs WHERE next_scheduled_at <= NOW() FOR UPDATE
        S->>S: Calculate next occurrence scheduled_for time

        alt Downtime Detected (Recovery Catch-up Check)
            Note over S: Missed window policy verification (Configurable Grace Window Default: 15m)
            alt Policy = RUN_ONCE
                alt Missed run is within 15 minutes of scheduled time
                    S->>DB: INSERT INTO jobs (project_id, queue_id, cron_config_id, scheduled_for, status='QUEUED')
                else Missed run is older than 15 minutes
                    Note over S: Skip missed occurrence, calculate next natural interval
                end
            alt Policy = FORCE_RUN
                S->>DB: INSERT INTO jobs (project_id, queue_id, cron_config_id, scheduled_for, status='QUEUED')
            alt Policy = SKIP
                Note over S: Skip missed run completely, proceed to calculate next natural runtime
            end
        else Natural Run Interval
            S->>DB: INSERT INTO jobs (project_id, queue_id, cron_config_id, scheduled_for, status='QUEUED')
        end

        alt Uniqueness Conflict: UNIQUE(cron_config_id, scheduled_for)
            DB-->>S: UNIQUE Constraint Violation (Occurrence already exists)
            S->>DB: Rollback Transaction (Conflict handled safely, no duplicate job queued)
        else Commit Success
            S->>DB: UPDATE cron_configs SET last_scheduled_at = next_scheduled_at, next_scheduled_at = calculated_next_time WHERE id = config_id
            S->>DB: Commit Transaction
        end
    end
```

---

### 2.5 Batch Child Completion & Callback Resolution Flow
This flow maps out how child jobs report completion, how BatchManager evaluates terminal state progress, and how callback tasks are dynamically scheduled.

```mermaid
sequenceDiagram
    autonumber
    participant EX as Executor
    participant BM as BatchManager
    participant DB as PostgreSQL DB

    EX->>DB: Update child job status to COMPLETED / CANCELLED / DLQ (Verified with Fencing Token)
    activate BM

    BM->>DB: Begin Transaction
    Note over BM,DB: Lock batch row FOR UPDATE to prevent race conditions on concurrent child transitions
    BM->>DB: SELECT status, callback_job_id FROM batches WHERE id = batch_id FOR UPDATE

    alt Batch is not already resolved (status = 'RUNNING')
        BM->>DB: SELECT status FROM jobs WHERE batch_id = batch_id
        DB-->>BM: Return child job statuses (COMPLETED, CANCELLED, DLQ, RUNNING, CLAIMED, etc.)

        alt All child jobs are terminal (COMPLETED, CANCELLED, or DLQ)
            alt 100% of child jobs are COMPLETED
                BM->>DB: UPDATE batches SET status = 'SUCCESS', finished_at = NOW() WHERE id = batch_id
            else At least one child is DLQ or CANCELLED
                BM->>DB: UPDATE batches SET status = 'FAILED', finished_at = NOW() WHERE id = batch_id
            end

            Note over BM: Evaluate callback trigger conditions (ALWAYS / ON_SUCCESS / ON_FAILURE / NEVER)
            alt Callback matches Batch outcome
                BM->>DB: INSERT INTO jobs (project_id, queue_id, batch_id, target_handler, payload, status='QUEUED') -- Create callback job
                BM->>DB: UPDATE batches SET callback_job_id = callback_job.id WHERE id = batch_id
            end
        end
    end
    BM->>DB: Commit Transaction
    deactivate BM
```

---

## 3. Interaction Correctness Rules

### Rule 1: Deterministic Lock Acquisition Order
To eliminate inter-plane transaction deadlocks when locking resources concurrently across multiple components, the platform must acquire locks in a globally defined hierarchical order:
1. **Queues Lock**: Acquired first (e.g. `queues FOR UPDATE` ordered by `q.id` during claim operations) to lock queue concurrency state.
2. **Jobs Lock**: Acquired second (e.g. `jobs FOR UPDATE` on specific job rows during claiming or status transition).
3. **Batches Lock**: Acquired third (e.g. `batches FOR UPDATE` on batch header records during child completion checks).

Transactions must never attempt to acquire locks in a reversed order (e.g. locking a batch record then attempting to lock jobs).

### Rule 2: Job Transition Authorization and Fencing Scope
Not all state transitions require worker fencing tokens. The token verification is scoped strictly based on ownership and authority boundaries:
- **Worker-Owned Execution Transitions**: Any transition initiated by an active worker process (e.g., claiming a job, heartbeating to `RUNNING`, or completing/failing to `COMPLETED`/`FAILED`) **must** verify the `ownership_token` conditionally in the `WHERE` clause. This protects the database from stale/revoked execution writes.
- **Reaper Recovery Transitions**: The Reaper daemon explicitly revokes worker ownership by setting `worker_id = NULL` and `ownership_token = NULL`. The Reaper does not verify the worker's token; its authority is governed by PostgreSQL transaction timing checks on expired worker heartbeat values.
- **API Cancellation Transitions**: Cancel operations requested via the FastAPI Control Plane set job status to `CANCELLED` and clear the worker and token references (`worker_id = NULL`, `ownership_token = NULL`). This is an authorized control action that overrides active execution claims.
- **Scheduler Job Creation**: Creation of scheduled cron occurrences is governed by unique constraint checks (`idx_jobs_cron_occurrence`) and cron configuration lock timings, rather than fencing checks.
