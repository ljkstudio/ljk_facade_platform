import { useState } from "react";
import { AdaptiveMoldView } from "./views/AdaptiveMoldView";
import { ProjectBoard } from "./views/ProjectBoard";

type View = "mold" | "projects";

export default function App() {
  const [view, setView] = useState<View>("mold");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>LJK Facade Platform</h1>
        <button
          className={`nav-btn ${view === "mold" ? "active" : ""}`}
          onClick={() => setView("mold")}
        >
          AdaptiveMold v1
        </button>
        <button
          className={`nav-btn ${view === "projects" ? "active" : ""}`}
          onClick={() => setView("projects")}
        >
          프로젝트 보드
        </button>
      </aside>
      <main className="main">
        {view === "mold" ? <AdaptiveMoldView /> : <ProjectBoard />}
      </main>
    </div>
  );
}
