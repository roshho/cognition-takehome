import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "@portal/platform";
import type { components } from "../api/schema";

type Tool = components["schemas"]["ToolOut"];
type Summary = components["schemas"]["DashboardSummary"];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function HomePage() {
  const { user } = useAuth();
  const [tools, setTools] = useState<Tool[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    api.GET("/api/tools").then(({ data }) => {
      if (data) setTools(data);
    });
    api.GET("/api/dashboard/summary").then(({ data }) => {
      if (data) setSummary(data);
    });
  }, []);

  return (
    <div>
      <div className="dash-header">
        <h2>
          {greeting()}, {user?.display_name}
        </h2>
        <p className="muted">
          Here's what's happening across your tools — filtered by your{" "}
          <span className="role-badge">{user?.role}</span> role on the server.
        </p>
      </div>

      <div className="tool-grid">
        {tools.map((t) => {
          const stats = summary?.stats[t.id] ?? [];
          return (
            <Link key={t.id} to={t.path} className="tool-card card">
              <h3>{t.name}</h3>
              <p className="muted">{t.description}</p>
              {stats.length > 0 && (
                <div className="stat-strip">
                  {stats.map((st) => (
                    <div
                      key={st.label}
                      className={`stat-box${st.tone ? ` stat-${st.tone}` : ""}`}
                    >
                      <span className="stat-num">{st.value}</span>
                      <span className="stat-label">{st.label}</span>
                    </div>
                  ))}
                </div>
              )}
              <span className="tool-open">Open →</span>
            </Link>
          );
        })}
        {tools.length === 0 && (
          <p className="muted">No tools available for your role.</p>
        )}
      </div>

      {summary && summary.recent_activity.length > 0 && (
        <div className="card activity-card">
          <div className="activity-head">
            <h3>Recent activity</h3>
            <Link to="/audit">View all →</Link>
          </div>
          <ul className="activity-list">
            {summary.recent_activity.map((a) => (
              <li key={a.id} className="activity-row">
                <span className="activity-action">
                  <strong>{a.actor}</strong> {a.action}
                  {a.entity_id ? ` ${a.entity} ${a.entity_id}` : ` ${a.entity}`}
                </span>
                <span className="muted">{a.created_at.replace("T", " ")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
