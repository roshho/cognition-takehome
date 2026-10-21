import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Tool {
  id: string;
  name: string;
  description: string;
  path: string;
  roles: string[];
}

export default function HomePage() {
  const { user } = useAuth();
  const [tools, setTools] = useState<Tool[]>([]);

  useEffect(() => {
    api.GET("/api/tools").then(({ data }) => {
      if (data) setTools(data as Tool[]);
    });
  }, []);

  return (
    <div>
      <h2>Your tools</h2>
      <p className="muted">
        Signed in as {user?.display_name} ({user?.role}). Tools are filtered by
        role on the server.
      </p>
      <div className="tool-grid">
        {tools.map((t) => (
          <Link key={t.id} to={t.path} className="tool-card card">
            <h3>{t.name}</h3>
            <p className="muted">{t.description}</p>
            <span className="tool-open">Open →</span>
          </Link>
        ))}
        {tools.length === 0 && (
          <p className="muted">No tools available for your role.</p>
        )}
      </div>
    </div>
  );
}
