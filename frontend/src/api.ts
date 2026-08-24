// Thin client for the FlowForge AI Control Plane API.
// Every function here maps 1:1 to a real backend route in flowforge_ai/control_plane/.

const BASE_URL = "http://127.0.0.1:8000";

export function getToken(): string | null {
  return localStorage.getItem("ff_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("ff_token", token);
  else localStorage.removeItem("ff_token");
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (options.body && !(options.body instanceof URLSearchParams)) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* body wasn't JSON — keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Types mirroring the backend Pydantic response models ----

export interface UserOut {
  id: string;
  username: string;
}

export interface ProjectOut {
  id: string;
  name: string;
}

export interface QueueOut {
  id: string;
  project_id: string;
  name: string;
  concurrency_limit: number;
  created_at: string;
}

export interface JobOut {
  id: string;
  status: string;
  queue_id: string;
  target_handler: string;
  payload?: string | null;
  priority: number;
  retries_total: number;
  retries_remaining: number;
  created_at: string;
  scheduled_for: string;
  claimed_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkerOut {
  id: string;
  hostname: string;
  capacity: number;
  status: string;
  last_heartbeat_at: string;
  registered_at: string;
}

export interface BatchOut {
  batch_id: string;
  status: string;
  total_jobs: number;
  created_at: string;
}

export interface BatchDetailOut {
  batch_id: string;
  status: string;
  progress: Record<string, number>;
  created_at: string;
  finished_at?: string | null;
}

export interface CronOut {
  id: string;
  cron_expression: string;
  missed_run_policy: string;
  next_scheduled_at?: string | null;
}

export interface DiagnosticsOut {
  job_id: string;
  diagnostic_status: string;
  error_summary?: string | null;
  root_cause?: string | null;
  remediation_suggestion?: string | null;
  analyzed_at?: string | null;
}

// ---- Auth ----

export const api = {
  register: (username: string, password: string) =>
    request<UserOut>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  login: async (username: string, password: string) => {
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);
    const data = await request<{ access_token: string; token_type: string }>(
      "/api/v1/auth/login",
      { method: "POST", body }
    );
    setToken(data.access_token);
    return data;
  },

  logout: () => setToken(null),

  // ---- Projects ----
  listProjects: () => request<ProjectOut[]>("/api/v1/projects"),
  createProject: (name: string) =>
    request<ProjectOut>("/api/v1/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (projectId: string) => request<ProjectOut>(`/api/v1/projects/${projectId}`),

  // ---- Queues ----
  listQueues: (projectId: string) =>
    request<QueueOut[]>(`/api/v1/projects/${projectId}/queues`),
  createQueue: (projectId: string, name: string, concurrencyLimit: number) =>
    request<QueueOut>(`/api/v1/projects/${projectId}/queues`, {
      method: "POST",
      body: JSON.stringify({ name, concurrency_limit: concurrencyLimit }),
    }),

  // ---- Jobs ----
  listJobs: (projectId: string, filters?: { queueName?: string; status?: string }) => {
    const params = new URLSearchParams();
    if (filters?.queueName) params.set("queue_name", filters.queueName);
    if (filters?.status) params.set("status", filters.status);
    const qs = params.toString();
    return request<JobOut[]>(`/api/v1/projects/${projectId}/jobs${qs ? `?${qs}` : ""}`);
  },
  submitJob: (
    projectId: string,
    job: {
      queue_name: string;
      target_handler: string;
      payload: Record<string, unknown>;
      priority?: number;
      retries?: number;
      delay_seconds?: number;
    },
    idempotencyKey?: string
  ) =>
    request<JobOut>(`/api/v1/projects/${projectId}/jobs`, {
      method: "POST",
      body: JSON.stringify(job),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    }),
  getJob: (projectId: string, jobId: string) =>
    request<JobOut>(`/api/v1/projects/${projectId}/jobs/${jobId}`),
  cancelJob: (projectId: string, jobId: string) =>
    request<{ id: string; status: string }>(`/api/v1/projects/${projectId}/jobs/${jobId}/cancel`, {
      method: "POST",
    }),
  getDiagnostics: (projectId: string, jobId: string) =>
    request<DiagnosticsOut>(`/api/v1/projects/${projectId}/jobs/${jobId}/diagnostics`),

  // ---- DLQ ----
  listDlq: (projectId: string) => request<JobOut[]>(`/api/v1/projects/${projectId}/dlq`),
  requeueDlq: (projectId: string, jobId: string) =>
    request<JobOut>(`/api/v1/projects/${projectId}/dlq/${jobId}/requeue`, { method: "POST" }),

  // ---- Batches ----
  createBatch: (
    projectId: string,
    jobs: Array<{ queue_name: string; target_handler: string; payload: Record<string, unknown> }>
  ) =>
    request<BatchOut>(`/api/v1/projects/${projectId}/batches`, {
      method: "POST",
      body: JSON.stringify({ jobs }),
    }),
  getBatch: (projectId: string, batchId: string) =>
    request<BatchDetailOut>(`/api/v1/projects/${projectId}/batches/${batchId}`),

  // ---- Cron ----
  createCron: (
    projectId: string,
    cron: { cron_expression: string; queue_name: string; target_handler: string; payload: Record<string, unknown> }
  ) =>
    request<CronOut>(`/api/v1/projects/${projectId}/cron`, {
      method: "POST",
      body: JSON.stringify(cron),
    }),
  deleteCron: (projectId: string, cronId: string) =>
    request<{ message: string }>(`/api/v1/projects/${projectId}/cron/${cronId}`, { method: "DELETE" }),

  // ---- Workers ----
  listWorkers: () => request<WorkerOut[]>("/api/v1/workers"),
};

export { ApiError };
