import { Fragment, FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  api,
  BatchDetailOut,
  CronOut,
  DiagnosticsOut,
  JobOut,
  ProjectOut,
  QueueOut,
} from "../api";
import StatusBadge from "../components/StatusBadge";

type Tab = "queues" | "jobs" | "dlq" | "batches" | "cron";

export default function ProjectView() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<ProjectOut | null>(null);
  const [queues, setQueues] = useState<QueueOut[]>([]);
  const [tab, setTab] = useState<Tab>("jobs");
  const [error, setError] = useState<string | null>(null);

  const queueNameById = useMemo(() => {
    const map: Record<string, string> = {};
    queues.forEach((q) => (map[q.id] = q.name));
    return map;
  }, [queues]);

  async function loadHeader() {
    if (!projectId) return;
    try {
      const [proj, qs] = await Promise.all([api.getProject(projectId), api.listQueues(projectId)]);
      setProject(proj);
      setQueues(qs);
    } catch (err: any) {
      setError(err.message ?? "Could not load project");
    }
  }

  useEffect(() => {
    loadHeader();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  if (!projectId) return null;

  return (
    <div className="page">
      <div className="page-header">
        <h1>{project?.name ?? "Loading…"}</h1>
        <span className="muted mono">{projectId}</span>
      </div>
      {error && <div className="alert alert-error">{error}</div>}

      <div className="tabs">
        {(["jobs", "queues", "dlq", "batches", "cron"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? "tab-active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "dlq" ? "Dead Letter Queue" : t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "queues" && (
        <QueuesTab projectId={projectId} queues={queues} onChanged={loadHeader} />
      )}
      {tab === "jobs" && (
        <JobsTab projectId={projectId} queues={queues} queueNameById={queueNameById} />
      )}
      {tab === "dlq" && <DlqTab projectId={projectId} queueNameById={queueNameById} />}
      {tab === "batches" && <BatchesTab projectId={projectId} queues={queues} />}
      {tab === "cron" && <CronTab projectId={projectId} queues={queues} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Queues
// ---------------------------------------------------------------------------

function QueuesTab({
  projectId,
  queues,
  onChanged,
}: {
  projectId: string;
  queues: QueueOut[];
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [limit, setLimit] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createQueue(projectId, name.trim(), limit);
      setName("");
      setLimit(1);
      onChanged();
    } catch (err: any) {
      setError(err.message ?? "Could not create queue");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form className="inline-form" onSubmit={onCreate}>
        <input placeholder="Queue name (e.g. emails)" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          type="number"
          min={1}
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          title="Concurrency limit"
          style={{ width: 140 }}
        />
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create queue"}
        </button>
      </form>
      {error && <div className="alert alert-error">{error}</div>}

      {queues.length === 0 ? (
        <div className="empty-state">
          <p>No queues yet.</p>
          <p className="muted">Create one above before you can submit jobs.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Concurrency limit</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {queues.map((q) => (
              <tr key={q.id}>
                <td>{q.name}</td>
                <td>{q.concurrency_limit}</td>
                <td>{new Date(q.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

function JobsTab({
  projectId,
  queues,
  queueNameById,
}: {
  projectId: string;
  queues: QueueOut[];
  queueNameById: Record<string, string>;
}) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [diagnostics, setDiagnostics] = useState<Record<string, DiagnosticsOut | "none">>({});

  // submit form
  const [queueName, setQueueName] = useState("");
  const [handler, setHandler] = useState("");
  const [payload, setPayload] = useState("{}");
  const [priority, setPriority] = useState(0);
  const [retries, setRetries] = useState(0);
  const [delaySeconds, setDelaySeconds] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setJobs(await api.listJobs(projectId, { status: statusFilter || undefined }));
    } catch (err: any) {
      setError(err.message ?? "Could not load jobs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, statusFilter]);

  async function onSubmitJob(e: FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    let parsedPayload: Record<string, unknown>;
    try {
      parsedPayload = payload.trim() ? JSON.parse(payload) : {};
    } catch {
      setSubmitError("Payload must be valid JSON.");
      return;
    }
    setSubmitting(true);
    try {
      await api.submitJob(projectId, {
        queue_name: queueName,
        target_handler: handler,
        payload: parsedPayload,
        priority,
        retries,
        delay_seconds: delaySeconds,
      });
      setHandler("");
      setPayload("{}");
      await load();
    } catch (err: any) {
      setSubmitError(err.message ?? "Could not submit job");
    } finally {
      setSubmitting(false);
    }
  }

  async function onCancel(jobId: string) {
    try {
      await api.cancelJob(projectId, jobId);
      await load();
    } catch (err: any) {
      setError(err.message ?? "Could not cancel job");
    }
  }

  async function onViewDiagnostics(jobId: string) {
    try {
      const d = await api.getDiagnostics(projectId, jobId);
      setDiagnostics((prev) => ({ ...prev, [jobId]: d }));
    } catch {
      setDiagnostics((prev) => ({ ...prev, [jobId]: "none" }));
    }
  }

  return (
    <div>
      <form className="card form-card" onSubmit={onSubmitJob}>
        <h3>Submit a job</h3>
        {submitError && <div className="alert alert-error">{submitError}</div>}
        <div className="form-row">
          <label>
            Queue
            <select value={queueName} onChange={(e) => setQueueName(e.target.value)} required>
              <option value="" disabled>
                Select a queue…
              </option>
              {queues.map((q) => (
                <option key={q.id} value={q.name}>
                  {q.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Target handler
            <input
              placeholder="e.g. tasks.send_email"
              value={handler}
              onChange={(e) => setHandler(e.target.value)}
              required
            />
          </label>
        </div>
        <label>
          Payload (JSON)
          <textarea rows={3} value={payload} onChange={(e) => setPayload(e.target.value)} />
        </label>
        <div className="form-row">
          <label>
            Priority
            <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
          </label>
          <label>
            Retries
            <input type="number" min={0} value={retries} onChange={(e) => setRetries(Number(e.target.value))} />
          </label>
          <label>
            Delay (seconds)
            <input
              type="number"
              min={0}
              value={delaySeconds}
              onChange={(e) => setDelaySeconds(Number(e.target.value))}
            />
          </label>
        </div>
        <button className="btn btn-primary" type="submit" disabled={submitting || queues.length === 0}>
          {submitting ? "Submitting…" : "Submit job"}
        </button>
        {queues.length === 0 && <p className="muted">Create a queue first (Queues tab).</p>}
      </form>

      <div className="list-toolbar">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {["QUEUED", "CLAIMED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "DLQ"].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button className="btn btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <p>No jobs yet.</p>
          <p className="muted">Submit one using the form above.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Handler</th>
              <th>Queue</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Retries</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <Fragment key={j.id}>
                <tr>
                  <td className="mono">{j.target_handler}</td>
                  <td>{queueNameById[j.queue_id] ?? j.queue_id.slice(0, 8)}</td>
                  <td>
                    <StatusBadge status={j.status} />
                  </td>
                  <td>{j.priority}</td>
                  <td>
                    {j.retries_remaining}/{j.retries_total}
                  </td>
                  <td>{new Date(j.created_at).toLocaleString()}</td>
                  <td className="actions">
                    {["QUEUED", "CLAIMED", "RUNNING"].includes(j.status) && (
                      <button className="btn btn-ghost btn-sm" onClick={() => onCancel(j.id)}>
                        Cancel
                      </button>
                    )}
                    {["FAILED", "DLQ"].includes(j.status) && (
                      <button className="btn btn-ghost btn-sm" onClick={() => onViewDiagnostics(j.id)}>
                        Diagnostics
                      </button>
                    )}
                  </td>
                </tr>
                {diagnostics[j.id] && (
                  <tr key={`${j.id}-diag`}>
                    <td colSpan={7}>
                      {diagnostics[j.id] === "none" ? (
                        <span className="muted">No AI diagnostics recorded for this job yet.</span>
                      ) : (
                        <div className="diagnostics-box">
                          <strong>Root cause:</strong> {(diagnostics[j.id] as DiagnosticsOut).root_cause ?? "—"}
                          <br />
                          <strong>Summary:</strong>{" "}
                          {(diagnostics[j.id] as DiagnosticsOut).error_summary ?? "—"}
                          <br />
                          <strong>Suggested fix:</strong>{" "}
                          {(diagnostics[j.id] as DiagnosticsOut).remediation_suggestion ?? "—"}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DLQ
// ---------------------------------------------------------------------------

function DlqTab({
  projectId,
  queueNameById,
}: {
  projectId: string;
  queueNameById: Record<string, string>;
}) {
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setJobs(await api.listDlq(projectId));
      setError(null);
    } catch (err: any) {
      setError(err.message ?? "Could not load DLQ");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function onRequeue(jobId: string) {
    try {
      await api.requeueDlq(projectId, jobId);
      await load();
    } catch (err: any) {
      setError(err.message ?? "Could not requeue job");
    }
  }

  return (
    <div>
      <p className="muted">
        Jobs land here after exhausting all retries. Requeue resets attempts and puts the job back at
        the front of its queue.
      </p>
      {error && <div className="alert alert-error">{error}</div>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : jobs.length === 0 ? (
        <div className="empty-state">
          <p>Dead letter queue is empty. Nothing to fix — for now.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Handler</th>
              <th>Queue</th>
              <th>Retries used</th>
              <th>Failed at</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="mono">{j.target_handler}</td>
                <td>{queueNameById[j.queue_id] ?? j.queue_id.slice(0, 8)}</td>
                <td>{j.retries_total}</td>
                <td>{j.finished_at ? new Date(j.finished_at).toLocaleString() : "—"}</td>
                <td>
                  <button className="btn btn-primary btn-sm" onClick={() => onRequeue(j.id)}>
                    Requeue
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Batches
// ---------------------------------------------------------------------------

function storageKey(projectId: string, kind: "batches" | "cron") {
  return `ff_${kind}_${projectId}`;
}

function BatchesTab({ projectId, queues }: { projectId: string; queues: QueueOut[] }) {
  const [knownIds, setKnownIds] = useState<string[]>(
    () => JSON.parse(localStorage.getItem(storageKey(projectId, "batches")) ?? "[]")
  );
  const [details, setDetails] = useState<Record<string, BatchDetailOut>>({});
  const [queueName, setQueueName] = useState("");
  const [handler, setHandler] = useState("");
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refreshDetails(ids: string[]) {
    const entries = await Promise.all(
      ids.map(async (id) => {
        try {
          return [id, await api.getBatch(projectId, id)] as const;
        } catch {
          return null;
        }
      })
    );
    const map: Record<string, BatchDetailOut> = {};
    entries.forEach((e) => e && (map[e[0]] = e[1]));
    setDetails(map);
  }

  useEffect(() => {
    if (knownIds.length) refreshDetails(knownIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const jobs = Array.from({ length: count }, (_, i) => ({
        queue_name: queueName,
        target_handler: handler,
        payload: { index: i },
      }));
      const batch = await api.createBatch(projectId, jobs);
      const next = [batch.batch_id, ...knownIds];
      setKnownIds(next);
      localStorage.setItem(storageKey(projectId, "batches"), JSON.stringify(next));
      await refreshDetails(next);
    } catch (err: any) {
      setError(err.message ?? "Could not create batch");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form className="card form-card" onSubmit={onCreate}>
        <h3>Create a batch</h3>
        <p className="muted">
          Submits several jobs at once, tracked as one unit with combined progress.
        </p>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="form-row">
          <label>
            Queue
            <select value={queueName} onChange={(e) => setQueueName(e.target.value)} required>
              <option value="" disabled>
                Select a queue…
              </option>
              {queues.map((q) => (
                <option key={q.id} value={q.name}>
                  {q.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Target handler
            <input value={handler} onChange={(e) => setHandler(e.target.value)} required />
          </label>
          <label>
            Job count
            <input
              type="number"
              min={1}
              max={50}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
          </label>
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy || queues.length === 0}>
          {busy ? "Creating…" : "Create batch"}
        </button>
      </form>

      {knownIds.length === 0 ? (
        <div className="empty-state">
          <p>No batches created from this browser yet.</p>
          <p className="muted">
            Batches created elsewhere won't show up here — there's no list-all-batches endpoint yet,
            so this console only remembers batches it created itself.
          </p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Batch ID</th>
              <th>Status</th>
              <th>Progress</th>
            </tr>
          </thead>
          <tbody>
            {knownIds.map((id) => {
              const d = details[id];
              return (
                <tr key={id}>
                  <td className="mono">{id.slice(0, 12)}…</td>
                  <td>{d ? <StatusBadge status={d.status} /> : "—"}</td>
                  <td>
                    {d
                      ? `${d.progress.completed ?? 0}/${d.progress.total ?? 0} done, ${
                          d.progress.failed_dlq ?? 0
                        } failed`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cron
// ---------------------------------------------------------------------------

function CronTab({ projectId, queues }: { projectId: string; queues: QueueOut[] }) {
  const [known, setKnown] = useState<CronOut[]>(
    () => JSON.parse(localStorage.getItem(storageKey(projectId, "cron")) ?? "[]")
  );
  const [expr, setExpr] = useState("*/5 * * * *");
  const [queueName, setQueueName] = useState("");
  const [handler, setHandler] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function persist(next: CronOut[]) {
    setKnown(next);
    localStorage.setItem(storageKey(projectId, "cron"), JSON.stringify(next));
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const cron = await api.createCron(projectId, {
        cron_expression: expr,
        queue_name: queueName,
        target_handler: handler,
        payload: {},
      });
      persist([cron, ...known]);
      setHandler("");
    } catch (err: any) {
      setError(err.message ?? "Could not create cron schedule");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: string) {
    try {
      await api.deleteCron(projectId, id);
      persist(known.filter((c) => c.id !== id));
    } catch (err: any) {
      setError(err.message ?? "Could not delete cron schedule");
    }
  }

  return (
    <div>
      <form className="card form-card" onSubmit={onCreate}>
        <h3>Schedule a recurring job</h3>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="form-row">
          <label>
            Cron expression
            <input value={expr} onChange={(e) => setExpr(e.target.value)} required />
          </label>
          <label>
            Queue
            <select value={queueName} onChange={(e) => setQueueName(e.target.value)} required>
              <option value="" disabled>
                Select a queue…
              </option>
              {queues.map((q) => (
                <option key={q.id} value={q.name}>
                  {q.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Target handler
            <input value={handler} onChange={(e) => setHandler(e.target.value)} required />
          </label>
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy || queues.length === 0}>
          {busy ? "Scheduling…" : "Create schedule"}
        </button>
      </form>

      {known.length === 0 ? (
        <div className="empty-state">
          <p>No recurring schedules created from this browser yet.</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Expression</th>
              <th>Missed-run policy</th>
              <th>Next run</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {known.map((c) => (
              <tr key={c.id}>
                <td className="mono">{c.cron_expression}</td>
                <td>{c.missed_run_policy}</td>
                <td>{c.next_scheduled_at ? new Date(c.next_scheduled_at).toLocaleString() : "—"}</td>
                <td>
                  <button className="btn btn-ghost btn-sm" onClick={() => onDelete(c.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
