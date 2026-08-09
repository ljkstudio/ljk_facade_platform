import { useEffect, useState } from "react";
import { api, type ProjectSummary } from "../api/client";

export function ProjectBoard() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="card">
      <h2>프로젝트 보드</h2>
      {error && <p className="error-text">{error}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>프로젝트</th>
            <th>패널</th>
            <th>상태</th>
            <th>액추에이터</th>
            <th>마지막 동기화</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((p) => (
            <tr key={p.project_id}>
              <td>{p.project_name}</td>
              <td>{p.panel_name || "—"}</td>
              <td>{p.status}</td>
              <td>{p.actuator_count || "—"}</td>
              <td>{p.last_sync_at ? new Date(p.last_sync_at).toLocaleString() : "—"}</td>
            </tr>
          ))}
          {projects.length === 0 && !error && (
            <tr>
              <td colSpan={5}>프로젝트 없음 — GH에서 sync 후 표시됩니다.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
