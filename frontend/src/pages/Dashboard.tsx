import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ProjectOut } from "../api";

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setProjects(await api.listProjects());
    } catch (err: any) {
      setError(err.message ?? "Could not load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createProject(newName.trim());
      setNewName("");
      await load();
    } catch (err: any) {
      setError(err.message ?? "Could not create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Projects</h1>
        <p className="page-subtitle">
          Every job, queue, and worker in FlowForge belongs to a project. Create one to get started.
        </p>
      </div>

      <form className="inline-form" onSubmit={onCreate}>
        <input
          placeholder="New project name (e.g. billing-service)"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create project"}
        </button>
      </form>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <p className="muted">Loading…</p>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <p>You don't have any projects yet.</p>
          <p className="muted">Create your first project above — you'll be its owner automatically.</p>
        </div>
      ) : (
        <div className="card-grid">
          {projects.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="project-card">
              <h3>{p.name}</h3>
              <span className="muted mono">{p.id}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
