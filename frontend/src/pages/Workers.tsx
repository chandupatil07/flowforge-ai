import { useEffect, useState } from "react";
import { api, WorkerOut } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Workers() {
  const [workers, setWorkers] = useState<WorkerOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setWorkers(await api.listWorkers());
      setError(null);
    } catch (err: any) {
      setError(err.message ?? "Could not load workers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <h1>Workers</h1>
        <p className="page-subtitle">
          Worker processes register here and send heartbeats while they claim and execute jobs.
          This list refreshes every 5 seconds.
        </p>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : workers.length === 0 ? (
        <div className="empty-state">
          <p>No workers registered yet.</p>
          <p className="muted">
            A worker process calls <code>POST /api/v1/workers/register</code> to appear here.
          </p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Hostname</th>
              <th>Status</th>
              <th>Capacity</th>
              <th>Last heartbeat</th>
              <th>Registered</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((w) => (
              <tr key={w.id}>
                <td>{w.hostname}</td>
                <td>
                  <StatusBadge status={w.status} />
                </td>
                <td>{w.capacity}</td>
                <td>{new Date(w.last_heartbeat_at).toLocaleTimeString()}</td>
                <td>{new Date(w.registered_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
