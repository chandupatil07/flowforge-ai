# FlowForge AI — API Contracts & Database Design

This document defines the concrete logical database schema, concurrency queries, security boundaries, error structures, and API endpoint contracts for **FlowForge AI**. It acts as the technical specification to guide implementation, ensuring consistency across database tables and web layers.

---

## Part A — Database Design

PostgreSQL is the single source of truth for all operational states. Below is the relational schema designed for the FlowForge AI MVP.

```
                  ┌───────────────┐
                  │     users     │
                  └───────┬───────┘
                          │ 1
                          │
                          │ *
                  ┌───────▼───────┐
                  │project_members│
                  └───────┬───────┘
                          │ *
                          │
                          │ 1
                  ┌───────▼───────┐
                  │   projects    │
                  └───────┬───────┘
                          │ 1
       ┌──────────────────┼──────────────────┐
       │ *                │ *                │ *
┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
│   queues    │    │   batches   │    │ cron_configs│
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │ 1                │ 1                │
       │                  │                  │
       │ *                │ *                │
┌──────▼──────────────────▼──────────────────▼──────┐
│                       jobs                        │
└──────┬──────────────────┬──────────────────┬──────┘
       │ 1                │ 1                │ 1
       │ (1:1)            │ (1:1)            │ (1:1)
┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
│  job_logs   │    │ai_diagnostics│   │   workers   │
└─────────────┘    └─────────────┘    └─────────────┘
```

### 1. Table Specifications

#### 1.1 `users`
- **Purpose**: Stores platform user records for authentication and role scoping.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `username`: `VARCHAR(100)` (NOT NULL, UNIQUE)
  - `password_hash`: `VARCHAR(255)` (NOT NULL)
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
- **Tenant Scope**: Global metadata.

#### 1.2 `projects`
- **Purpose**: Logical tenant boundary. All queues, jobs, and configurations belong to a project.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `name`: `VARCHAR(100)` (NOT NULL)
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
- **Tenant Scope**: Defines the root tenant namespace.

#### 1.3 `project_members`
- **Purpose**: Maps user access levels to projects (enforcing RBAC).
- **Columns**:
  - `project_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `projects.id` ON DELETE CASCADE)
  - `user_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `users.id` ON DELETE CASCADE)
  - `role`: `VARCHAR(50)` (NOT NULL) — Allowed values: `OWNER`, `DEVELOPER`, `OPERATOR`
- **Primary Key**: `(project_id, user_id)`
- **Tenant Scope**: Scoped to `project_id`.

#### 1.4 `queues`
- **Purpose**: Configures logical queue limits per project.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `project_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `projects.id` ON DELETE CASCADE)
  - `name`: `VARCHAR(100)` (NOT NULL)
  - `concurrency_limit`: `INTEGER` (NOT NULL, Default: 1)
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
- **Constraints**:
  - Unique: `UNIQUE(project_id, name)`
  - Unique: `UNIQUE(project_id, id)` — Enabled to support multi-column composite foreign keys.
  - Check: `CHECK (concurrency_limit > 0)`
- **Indexes**:
  - Unique index on `(project_id, name)`
- **Tenant Scope**: Scoped to `project_id`.

#### 1.5 `batches`
- **Purpose**: Groups related jobs to track batch progress and trigger completions.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `project_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `projects.id` ON DELETE CASCADE)
  - `status`: `VARCHAR(50)` (NOT NULL, Default: `'RUNNING'`) — Allowed values: `RUNNING`, `SUCCESS`, `FAILED`
  - `callback_handler`: `VARCHAR(255)` (NULLABLE) — Handler run on batch completion.
  - `callback_payload`: `JSONB` (NULLABLE) — Constraints: payload size must not exceed 100 KB.
  - `callback_trigger_condition`: `VARCHAR(50)` (NOT NULL, Default: `'ALWAYS'`) — Allowed: `ALWAYS`, `ON_SUCCESS`, `ON_FAILURE`, `NEVER`
  - `callback_job_id`: `UUID` (NULLABLE) — References the spawned callback job.
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
  - `finished_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
- **Constraints**:
  - Check: `CHECK (octet_length(callback_payload::text) <= 102400)`
  - Unique: `UNIQUE(project_id, id)` — Enabled to support multi-column composite foreign keys.
  - Foreign Key: `FOREIGN KEY (project_id, callback_job_id) REFERENCES jobs(project_id, id) ON DELETE SET NULL (callback_job_id)` — Enforces project-scoped callback reference consistency while preserving the non-null project_id boundary.
- **Tenant Scope**: Scoped to `project_id`.

#### 1.6 `jobs`
- **Purpose**: Central task record representing queued, active, and terminal jobs.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `project_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `projects.id` ON DELETE CASCADE)
  - `queue_id`: `UUID` (NOT NULL)
  - `batch_id`: `UUID` (NULLABLE)
  - `cron_config_id`: `UUID` (NULLABLE)
  - `target_handler`: `VARCHAR(255)` (NOT NULL)
  - `payload`: `JSONB` (NOT NULL) — Constraints: payload size must not exceed 100 KB.
  - `status`: `VARCHAR(50)` (NOT NULL, Default: `'QUEUED'`) — Allowed: `QUEUED`, `CLAIMED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `DLQ`
  - `priority`: `INTEGER` (NOT NULL, Default: 0)
  - `retries_total`: `INTEGER` (NOT NULL, Default: 0)
  - `retries_remaining`: `INTEGER` (NOT NULL, Default: 0)
  - `worker_id`: `UUID` (NULLABLE, FOREIGN KEY referencing `workers.id` ON DELETE SET NULL)
  - `ownership_token`: `UUID` (NULLABLE) — Fencing token generated upon claim lock.
  - `idempotency_key`: `VARCHAR(255)` (NULLABLE)
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
  - `scheduled_for`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
  - `claimed_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
  - `started_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
  - `finished_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
- **Constraints**:
  - Check: `CHECK (octet_length(payload::text) <= 102400)`
  - Check: `CHECK (retries_total >= 0 AND retries_remaining >= 0)`
  - Check: `CHECK (retries_remaining <= retries_total)`
  - Unique: `UNIQUE(project_id, id)` — Enabled to support multi-column reference checks.
  - Foreign Key: `FOREIGN KEY (project_id, queue_id) REFERENCES queues(project_id, id) ON DELETE RESTRICT` — Enforces project-scoped queue consistency.
  - Foreign Key: `FOREIGN KEY (project_id, batch_id) REFERENCES batches(project_id, id) ON DELETE SET NULL (batch_id)` — Enforces project-scoped batch consistency while preserving the non-null project_id boundary.
  - Foreign Key: `FOREIGN KEY (project_id, cron_config_id) REFERENCES cron_configs(project_id, id) ON DELETE SET NULL (cron_config_id)` — Enforces project-scoped cron config consistency while preserving the non-null project_id boundary.
- **Indexes**:
  - Partial Unique Index for Idempotency: `idx_jobs_idempotency` UNIQUE on `(project_id, idempotency_key)` WHERE `idempotency_key IS NOT NULL`
  - Partial Unique Index for Cron Occurrences: `idx_jobs_cron_occurrence` UNIQUE on `(cron_config_id, scheduled_for)` WHERE `cron_config_id IS NOT NULL`
  - Composite Index for Claim Polling: `idx_jobs_claim_polling` on `(status, scheduled_for, priority DESC, created_at ASC)` WHERE `status = 'QUEUED'`
- **Tenant Scope**: Scoped to `project_id`.

#### 1.7 `cron_configs`
- **Purpose**: Defines configuration templates for recurring jobs.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `project_id`: `UUID` (NOT NULL, FOREIGN KEY referencing `projects.id` ON DELETE CASCADE)
  - `queue_id`: `UUID` (NOT NULL)
  - `cron_expression`: `VARCHAR(100)` (NOT NULL)
  - `target_handler`: `VARCHAR(255)` (NOT NULL)
  - `payload`: `JSONB` (NOT NULL) — Constraints: payload size must not exceed 100 KB.
  - `missed_run_policy`: `VARCHAR(50)` (NOT NULL, Default: `'RUN_ONCE'`) — Allowed: `RUN_ONCE`, `FORCE_RUN`, `SKIP`
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
  - `last_scheduled_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
  - `next_scheduled_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
- **Constraints**:
  - Check: `CHECK (octet_length(payload::text) <= 102400)`
  - Unique: `UNIQUE(project_id, id)` — Enabled to support multi-column reference checks.
  - Foreign Key: `FOREIGN KEY (project_id, queue_id) REFERENCES queues(project_id, id) ON DELETE RESTRICT` — Enforces project-scoped queue consistency.
- **Tenant Scope**: Scoped to `project_id`.

#### 1.8 `workers`
- **Purpose**: Dynamic registry for monitoring worker capacity and cluster health.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY) — Generated by the worker coordinator client upon registration.
  - `hostname`: `VARCHAR(255)` (NOT NULL)
  - `capacity`: `INTEGER` (NOT NULL, Default: 1)
  - `status`: `VARCHAR(50)` (NOT NULL, Default: `'ACTIVE'`) — Allowed: `ACTIVE`, `OFFLINE`
  - `last_heartbeat_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
  - `registered_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
- **Constraints**:
  - Check: `CHECK (capacity > 0)`
- **Tenant Scope**: Shared infrastructure metadata (system-wide visibility).

#### 1.9 `job_logs`
- **Purpose**: Stores stdout/stderr outputs captured during process execution.
- **Columns**:
  - `id`: `UUID` (PRIMARY KEY, Default: `gen_random_uuid()`)
  - `job_id`: `UUID` (NOT NULL, UNIQUE, FOREIGN KEY referencing `jobs.id` ON DELETE CASCADE)
  - `content`: `TEXT` (NOT NULL) — Constraints: size must not exceed 100 KB.
  - `created_at`: `TIMESTAMP WITH TIME ZONE` (NOT NULL, Default: `NOW()`)
- **Constraints**:
  - Check: `CHECK (octet_length(content) <= 102400)`
- **Tenant Scope**: Indirectly scoped to project via `job_id`.

#### 1.10 `ai_diagnostics`
- **Purpose**: Stores out-of-band diagnostic analysis for failed job logs.
- **Columns**:
  - `job_id`: `UUID` (PRIMARY KEY)
  - `project_id`: `UUID` (NOT NULL)
  - `diagnostic_status`: `VARCHAR(50)` (NOT NULL, Default: `'NOT_REQUESTED'`) — Allowed: `NOT_REQUESTED`, `ANALYZING`, `COMPLETED`, `FAILED`, `UNAVAILABLE`
  - `error_summary`: `TEXT` (NULLABLE)
  - `root_cause`: `TEXT` (NULLABLE)
  - `remediation_suggestion`: `TEXT` (NULLABLE)
  - `analyzed_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
- **Constraints**:
  - Foreign Key: `FOREIGN KEY (project_id, job_id) REFERENCES jobs(project_id, id) ON DELETE CASCADE` — Enforces project-scoped job diagnostic consistency.
  - `error_summary`: `TEXT` (NULLABLE)
  - `root_cause`: `TEXT` (NULLABLE)
  - `remediation_suggestion`: `TEXT` (NULLABLE)
  - `analyzed_at`: `TIMESTAMP WITH TIME ZONE` (NULLABLE)
- **Tenant Scope**: Scoped to `project_id`.

---

### 2. Omitted Entities (MVP Rationale)
- **Separate Idempotency Table**: Omitted. Instead of maintaining an extra table, we enforce a partial unique constraint on `(project_id, idempotency_key)` directly in the `jobs` table. This allows the API to perform simple lookups on the target resource table without extra joins.
- **Separate Attempt/Execution Table**: Omitted. Retries are tracked via `retries_total` and `retries_remaining` columns directly on the `jobs` record. For the MVP, logging and debugging are satisfied by checking execution stdout/stderr in `job_logs`, avoiding write amplification on attempt tables.
- **Separate DLQ Table**: Omitted. Jobs routed to the Dead Letter Queue simply transition their status column to `'DLQ'`, preserving their original priorities, payloads, and execution history.

---

## Part B — Concurrency & Correctness

### 1. Atomic Job Claiming & Queue Concurrency
To claim a job atomically while respecting the concurrent job limit $N$ for its respective queue, the claiming process runs the following locked transaction query:

```sql
WITH locked_queues AS (
    -- Lock candidate queues that have pending jobs to serialize concurrency decisions per queue
    SELECT q.id, q.concurrency_limit
    FROM queues q
    WHERE q.id IN (
        SELECT DISTINCT queue_id
        FROM jobs
        WHERE status = 'QUEUED' AND scheduled_for <= NOW()
    )
    ORDER BY q.id -- Deterministic ordering to prevent deadlocks when locking multiple queues concurrently
    FOR UPDATE
),
active_counts AS (
    -- Count running or claimed executions active under locked candidate queues
    SELECT j.queue_id, COUNT(*) AS active_count
    FROM jobs j
    WHERE j.status IN ('CLAIMED', 'RUNNING')
      AND j.queue_id IN (SELECT id FROM locked_queues)
    GROUP BY j.queue_id
),
eligible_job AS (
    -- Select the single highest priority job from a queue that has remaining capacity
    SELECT j.id
    FROM jobs j
    JOIN locked_queues lq ON j.queue_id = lq.id
    LEFT JOIN active_counts ac ON j.queue_id = ac.queue_id
    WHERE j.status = 'QUEUED'
      AND j.scheduled_for <= NOW()
      AND COALESCE(ac.active_count, 0) < lq.concurrency_limit
    ORDER BY j.priority DESC, j.created_at ASC
    LIMIT 1
    FOR UPDATE OF j
)
-- Atomically transition status, write worker ownership, and issue fencing token
UPDATE jobs
SET status = 'CLAIMED',
    worker_id = :worker_id,
    ownership_token = :ownership_token,
    claimed_at = NOW()
WHERE id = (SELECT id FROM eligible_job)
RETURNING id, queue_id, target_handler, payload, ownership_token;
```

---

### 2. Ownership & Fencing Token Invariant
When updating job status (to `COMPLETED`, `FAILED`, or during heartbeat transitions to `RUNNING`), workers must verify their fencing token matches the active db record:

```sql
UPDATE jobs
SET status = 'COMPLETED',
    finished_at = NOW()
WHERE id = :job_id
  AND ownership_token = :ownership_token;
```
If the query updates `0` rows, ownership has been revoked by the Reaper during a heartbeat timeout. The executing worker must discard results, clean up local process footprints, and abort immediately.

---

### 3. Reaper Orphan Reclaiming
The Reaper daemon regularly queries heartbeats to reclaim orphaned jobs:

```sql
-- Sweep offline workers and transition their claimed/running jobs
UPDATE jobs
SET status = CASE WHEN retries_remaining > 0 THEN 'QUEUED' ELSE 'DLQ' END,
    retries_remaining = CASE WHEN retries_remaining > 0 THEN retries_remaining - 1 ELSE 0 END,
    worker_id = NULL,
    ownership_token = NULL,
    finished_at = CASE WHEN retries_remaining = 0 THEN NOW() ELSE NULL END
WHERE status IN ('CLAIMED', 'RUNNING')
  AND worker_id IN (
      SELECT id FROM workers
      WHERE status = 'OFFLINE'
         OR last_heartbeat_at < NOW() - INTERVAL '15 seconds' -- 15 seconds is a Design Default (configurable)
  );
```

---

## Part C — API Contracts

All API endpoints must be prefixed with `/api/v1`.

### 1. Authentication Endpoints

#### `POST /api/v1/auth/token`
- **Purpose**: Authenticates credentials and returns a JWT access token.
- **Authentication**: Public.
- **Request Body**:
  ```json
  {
    "username": "user123",
    "password": "securepassword"
  }
  ```
- **Success Response (200 OK)**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
- **Error Responses**:
  - `401 Unauthorized`: Invalid username or password.

---

### 2. Project Endpoints

#### `POST /api/v1/projects`
- **Purpose**: Creates a new project workspace.
- **Authentication**: Required (JWT).
- **Request Body**:
  ```json
  {
    "name": "Acme Job Workspace"
  }
  ```
- **Success Response (201 Created)**:
  ```json
  {
    "id": "e8a931a7-e17f-4402-98ba-d52f8c5b6ff8",
    "name": "Acme Job Workspace",
    "created_at": "2026-08-22T12:00:00Z"
  }
  ```
- **Error Responses**:
  - `400 Bad Request`: Validation failure.

#### `GET /api/v1/projects`
- **Purpose**: Lists all projects the authenticated user belongs to.
- **Authentication**: Required (JWT).
- **Success Response (200 OK)**:
  ```json
  [
    {
      "id": "e8a931a7-e17f-4402-98ba-d52f8c5b6ff8",
      "name": "Acme Job Workspace",
      "role": "OWNER"
    }
  ]
  ```

---

### 3. Queue Endpoints

#### `POST /api/v1/projects/{project_id}/queues`
- **Purpose**: Creates or updates queue configurations.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role on the project.
- **Request Body**:
  ```json
  {
    "name": "default-queue",
    "concurrency_limit": 5
  }
  ```
- **Success Response (201 Created)**:
  ```json
  {
    "id": "a8790cb9-31b3-4fba-a82f-ccb3922f3922",
    "project_id": "e8a931a7-e17f-4402-98ba-d52f8c5b6ff8",
    "name": "default-queue",
    "concurrency_limit": 5,
    "created_at": "2026-08-22T12:05:00Z"
  }
  ```
- **Error Responses**:
  - `403 Forbidden`: Unauthorized role.
  - `409 Conflict`: Queue name already exists in project.

---

### 4. Job Endpoints

#### `POST /api/v1/projects/{project_id}/jobs`
- **Purpose**: Submits a job execution request.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role on the project.
- **Rate-Limiting**: Yes (RateLimiter applies at this entry route).
- **Request Headers**:
  - `Idempotency-Key`: `idempotency-key-uuid` (Optional)
- **Request Body**:
  ```json
  {
    "queue_name": "default-queue",
    "target_handler": "tasks.send_email",
    "payload": {
      "to": "user@example.com",
      "template": "welcome"
    },
    "priority": 10,
    "retries": 3,
    "delay_seconds": 0
  }
  ```
- **Success Response (201 Created / 200 OK for Duplicate Idempotency)**:
  ```json
  {
    "id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
    "status": "QUEUED",
    "queue_name": "default-queue",
    "target_handler": "tasks.send_email",
    "priority": 10,
    "scheduled_for": "2026-08-22T12:10:00Z"
  }
  ```
- **Error Responses**:
  - `413 Payload Too Large`: Payload size exceeds 100 KB.
  - `422 Unprocessable Entity`: Validation failure.

#### `GET /api/v1/projects/{project_id}/jobs/{job_id}`
- **Purpose**: Fetches status and metadata details of a specific job.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER`, `DEVELOPER`, or `OPERATOR` role on the project.
- **Success Response (200 OK)**:
  ```json
  {
    "id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
    "status": "RUNNING",
    "queue_name": "default-queue",
    "target_handler": "tasks.send_email",
    "payload": { "to": "user@example.com", "template": "welcome" },
    "retries_total": 3,
    "retries_remaining": 2,
    "created_at": "2026-08-22T12:10:00Z",
    "started_at": "2026-08-22T12:10:05Z",
    "finished_at": null
  }
  ```

#### `POST /api/v1/projects/{project_id}/jobs/{job_id}/cancel`
- **Purpose**: Cancels a queued job or signals cancellation of running jobs.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role on the project.
- **Success Response (200 OK)**:
  ```json
  {
    "id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
    "status": "CANCELLED"
  }
  ```

---

### 5. Batch Endpoints

#### `POST /api/v1/projects/{project_id}/batches`
- **Purpose**: Groups and schedules a list of jobs as a single atomic batch.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role.
- **Request Body**:
  ```json
  {
    "jobs": [
      {
        "queue_name": "default-queue",
        "target_handler": "tasks.process_image",
        "payload": { "image_id": 1 }
      },
      {
        "queue_name": "default-queue",
        "target_handler": "tasks.process_image",
        "payload": { "image_id": 2 }
      }
    ],
    "callback_handler": "tasks.notify_batch_completion",
    "callback_payload": { "batch_ref": "images-v1" },
    "callback_trigger_condition": "ALWAYS"
  }
  ```
- **Success Response (201 Created)**:
  ```json
  {
    "batch_id": "b90cb3a8-4bb2-4aef-90cc-87b3a92a392b",
    "status": "RUNNING",
    "total_jobs": 2,
    "created_at": "2026-08-22T12:15:00Z"
  }
  ```

#### `GET /api/v1/projects/{project_id}/batches/{batch_id}`
- **Purpose**: Retrieves statistics and progress rates of a batch.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER`, `DEVELOPER`, or `OPERATOR` role.
- **Success Response (200 OK)**:
  ```json
  {
    "batch_id": "b90cb3a8-4bb2-4aef-90cc-87b3a92a392b",
    "status": "RUNNING",
    "progress": {
      "total": 100,
      "queued": 10,
      "claimed": 5,
      "running": 15,
      "completed": 65,
      "failed_dlq": 5
    },
    "created_at": "2026-08-22T12:15:00Z",
    "finished_at": null
  }
  ```

---

### 6. Cron / Scheduler Endpoints

#### `POST /api/v1/projects/{project_id}/cron`
- **Purpose**: Registers or updates a recurring cron job definition.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role.
- **Request Body**:
  ```json
  {
    "cron_expression": "*/5 * * * *",
    "queue_name": "default-queue",
    "target_handler": "tasks.db_backup",
    "payload": { "type": "daily" },
    "missed_run_policy": "RUN_ONCE"
  }
  ```
- **Success Response (201 Created)**:
  ```json
  {
    "id": "d983c2e1-4bb2-4abf-923f-8c3b9a02fae8",
    "cron_expression": "*/5 * * * *",
    "missed_run_policy": "RUN_ONCE",
    "next_scheduled_at": "2026-08-22T12:20:00Z"
  }
  ```

#### `DELETE /api/v1/projects/{project_id}/cron/{cron_id}`
- **Purpose**: Deletes a cron configuration, preventing future schedules.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role.
- **Success Response (200 OK)**:
  ```json
  {
    "message": "Cron configuration deleted successfully."
  }
  ```

---

### 7. Dead Letter Queue (DLQ) Endpoints

#### `GET /api/v1/projects/{project_id}/dlq`
- **Purpose**: Lists all jobs in the project workspace currently residing in the DLQ.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER`, `DEVELOPER`, or `OPERATOR` role.
- **Success Response (200 OK)**:
  ```json
  [
    {
      "id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
      "queue_name": "default-queue",
      "target_handler": "tasks.send_email",
      "failed_at": "2026-08-22T12:30:00Z",
      "retries_total": 3
    }
  ]
  ```

#### `POST /api/v1/projects/{project_id}/dlq/{job_id}/requeue`
- **Purpose**: Requeues a failed job from the DLQ back into the target queue.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER` or `DEVELOPER` role.
- **Success Response (200 OK)**:
  ```json
  {
    "id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
    "status": "QUEUED",
    "retries_remaining": 3
  }
  ```

---

### 8. AI Diagnostics Endpoints

#### `GET /api/v1/projects/{project_id}/jobs/{job_id}/diagnostics`
- **Purpose**: Retrieves AI failure analysis diagnostics for a failed task execution.
- **Authentication**: Required (JWT).
- **Authorization**: User must have `OWNER`, `DEVELOPER`, or `OPERATOR` role.
- **Success Response (200 OK)**:
  ```json
  {
    "job_id": "c71a329d-478e-4a6c-829d-aef234f9a0c1",
    "diagnostic_status": "COMPLETED",
    "error_summary": "Database connection timeout during SMTP query.",
    "root_cause": "SMTP host server failed to respond within 5000ms threshold.",
    "remediation_suggestion": "Verify mail configuration server host addresses or increase timeout settings.",
    "analyzed_at": "2026-08-22T12:35:00Z"
  }
  ```

---

## Part D — Security

- **JWT Authentication Contract**: Access tokens are signed using `HS256` (Design Default). API requests authenticate by passing `Authorization: Bearer <JWT_Token>` inside the headers.
- **Project-Scoped RBAC**: Enforced by mapping user relationships inside `project_members`.
  - `OWNER` / `DEVELOPER`: Full read/write authority across project jobs, queues, crons, batches, and DLQ requeues.
  - `OPERATOR`: Read-only access to view states, queues, logs, and diagnostic records (write capabilities are blocked).
- **Endpoint Protection Scope**: All routes except `POST /api/v1/auth/token` require authentication.
- **Payload Size Enforcement**: Fast checks are executed at the route input layer by rejecting requests immediately with an `HTTP 413 Payload Too Large` status code if headers or raw content measurements exceed 102,400 bytes (100 KB).
- **Rate-Limiting Boundary**: Protected API endpoints (specifically `POST /api/v1/projects/{project_id}/jobs`) are intercepted at the outer HTTP routing boundary before routing to controllers or database queries, avoiding system CPU exhaustion during attack loads.
- **Failure Responses**:
  - Unauthenticated requests yield `401 Unauthorized` with error code `UNAUTHENTICATED`.
  - Unauthorized RBAC checks yield `403 Forbidden` with error code `FORBIDDEN`.

---

## Part E — Error Contract

All errors returned by the API gateway follow a standardized JSON schema:

```json
{
  "error_code": "VALIDATION_FAILED",
  "message": "The payload provided violates size bounds.",
  "details": {
    "payload": "Job payload cannot exceed 100 KB size limit."
  }
}
```

### Common HTTP Status Meanings
- `400 Bad Request` (`BAD_REQUEST`): Client query parameter is missing or formatted invalidly.
- `401 Unauthorized` (`UNAUTHENTICATED`): JWT access token is expired, missing, or invalid.
- `403 Forbidden` (`FORBIDDEN`): User does not possess roles granting requested access in this project.
- `404 Not Found` (`NOT_FOUND`): Target resource (Job, Queue, Project) does not exist.
- `413 Payload Too Large` (`PAYLOAD_TOO_LARGE`): Job body size limit (100 KB) is exceeded.
- `422 Unprocessable Entity` (`VALIDATION_FAILED`): Input fails schema constraints (e.g. invalid cron format).
- `429 Too Many Requests` (`RATE_LIMIT_EXCEEDED`): Boundary rate limit threshold is exceeded.
- `500 Internal Server Error` (`INTERNAL_SERVER_ERROR`): Server encountered unexpected errors.

---

## Part F — Idempotency

When clients execute a job submission request:
- The endpoint queries `IdempotencyManager` using `(project_id, idempotency_key)` to check if an identical job entry exists in `jobs`.
- If an existing record is detected, the API returns the details of that existing job record with a `200 OK` status, avoiding duplicate work queueing.
- If no record matches, the job is written to `jobs`, and returns `201 Created`.
- **Concurrent Submissions (Race Handling)**: If two concurrent API requests submit the same `(project_id, idempotency_key)` simultaneously, database-level isolation and the unique index (`idx_jobs_idempotency`) will cause one transaction to commit successfully while the losing transaction triggers a unique constraint conflict. The API controller must catch this database conflict exception, query the successfully created job, and safely return it to the caller with a `200 OK` response without queueing any duplicate work.
- **Database Constraint**: `idx_jobs_idempotency` partial unique constraint:
  ```sql
  CREATE UNIQUE INDEX idx_jobs_idempotency
  ON jobs(project_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
  ```

---

## Part G — Batch & Callbacks

- **Terminal Batch State**: Checked dynamically upon child job execution terminal transitions.
  - A batch becomes terminal only when all child jobs associated with `batch_id` are in `COMPLETED`, `CANCELLED`, or `DLQ` states.
  - Resolves to `SUCCESS` if 100% of child job states are `COMPLETED`. Resolves to `FAILED` if at least one child job is in `DLQ` or is `CANCELLED`.
- **Callback Firing Rules**:
  - The `BatchManager` evaluates outcomes against `callback_trigger_condition` (`ALWAYS`, `ON_SUCCESS`, `ON_FAILURE`, `NEVER`).
  - If conditions are met, the manager registers a new job task in `jobs` with `target_handler = callback_handler` and `payload = callback_payload`, setting `callback_job_id` to link records.

---

## Part H — Cron

The database schema and scheduler daemon enforce cron execution rules using the `missed_run_policy` definitions:
- **`RUN_ONCE` (Default)**: Upon recovery, evaluate cron triggers against a **15-minute grace window** (Design Default). Catch up with exactly one job if the missed time is within 15 minutes; otherwise, skip and wait for the next cron interval.
- **`FORCE_RUN`**: Always schedules exactly one catch-up job execution immediately upon recovery, regardless of the downtime duration.
- **`SKIP`**: Discards all missed trigger occurrences during downtime, scheduling only the next upcoming natural interval.
- **Constraint**: `idx_jobs_cron_occurrence` partial unique constraint:
  ```sql
  CREATE UNIQUE INDEX idx_jobs_cron_occurrence
  ON jobs(cron_config_id, scheduled_for)
  WHERE cron_config_id IS NOT NULL;
  ```
  This constraint ensures that a scheduled cron runtime slot is never queued more than once, preventing concurrent schedulers or restarts from creating duplicate runs.

---

## Part I — Non-Goals

This document does **not** implement:
- Python application code, FastAPI router scripts, or controller logic.
- ORM model definitions or database migrations (e.g. Alembic python scripts).
- Multiprocessing/process execution pool codes.
- Local LLM prompt configurations, diagnostic client wrappers, or RAG models.
- Docker Compose containers, environment setups, or cloud configurations.
- Specific cron expression parser library choices (deferred to execution coding).
- Rate limit bucket algorithms or token bucket codes.
