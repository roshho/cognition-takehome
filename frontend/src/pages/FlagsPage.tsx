import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "@portal/platform";
import { DataTable } from "@portal/platform";

interface Flag {
  id: number;
  key: string;
  description: string;
  enabled_dev: boolean;
  enabled_staging: boolean;
  enabled_prod: boolean;
}

interface HistoryEntry {
  id: number;
  actor: string;
  action: string;
  before: string | null;
  after: string | null;
  created_at: string;
}

const ENVS = ["dev", "staging", "prod"] as const;

export default function FlagsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<Flag[]>([]);
  const [history, setHistory] = useState<HistoryEntry[] | null>(null);
  const [historyKey, setHistoryKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/api/flags");
    if (data) setRows(data as Flag[]);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (key: string, env: (typeof ENVS)[number]) => {
    setError(null);
    const { error } = await api.POST("/api/flags/{key}/toggle", {
      params: { path: { key } },
      body: { environment: env },
    });
    if (error) {
      const detail = (error as { detail?: string }).detail;
      setError(detail ?? "Toggle failed");
      return;
    }
    if (historyKey === key) await showHistory(key);
    await load();
  };

  const showHistory = async (key: string) => {
    setHistoryKey(key);
    const { data } = await api.GET("/api/flags/{key}/history", {
      params: { path: { key } },
    });
    setHistory((data as HistoryEntry[]) ?? []);
  };

  const envCell = (env: (typeof ENVS)[number]) => (f: Flag) => {
    const enabled = f[`enabled_${env}`];
    const locked =
      user?.role === "read_only" || (env === "prod" && user?.role !== "admin");
    return (
      <button
        className={`toggle ${enabled ? "on" : "off"}`}
        disabled={locked}
        title={locked ? (user?.role === "read_only" ? "Read-only account" : "Prod toggles require an admin") : `${env}: ${enabled ? "on" : "off"}`}
        onClick={() => toggle(f.key, env)}
      >
        {enabled ? "on" : "off"}
      </button>
    );
  };

  return (
    <div>
      <h2>Feature flags</h2>
      <p className="muted">
        Per-environment toggles. Prod changes need an admin; every change is
        audited — click a flag to see its history.
      </p>
      {error && <p className="form-error">{error}</p>}
      <DataTable<Flag>
        columns={[
          {
            key: "key",
            label: "Flag",
            render: (f) => (
              <button className="link-btn" onClick={() => showHistory(f.key)}>
                <code>{f.key}</code>
              </button>
            ),
          },
          { key: "description", label: "Description" },
          { key: "enabled_dev", label: "Dev", sortable: false, render: envCell("dev") },
          { key: "enabled_staging", label: "Staging", sortable: false, render: envCell("staging") },
          { key: "enabled_prod", label: "Prod", sortable: false, render: envCell("prod") },
        ]}
        rows={rows}
        filterPlaceholder="Filter flags…"
        filterValue={(f) => `${f.key} ${f.description}`}
      />
      {historyKey && (
        <div className="card flag-history">
          <h3>
            Change history — <code>{historyKey}</code>{" "}
            <button className="link-btn" onClick={() => { setHistoryKey(null); setHistory(null); }}>
              close
            </button>
          </h3>
          {history && history.length === 0 && (
            <p className="muted">No recorded changes yet.</p>
          )}
          {history?.map((h) => (
            <p key={h.id} className="note">
              <strong>{h.actor}</strong> <span className="muted">{h.created_at}</span>
              <br />
              <code className="diff">{h.before} → {h.after}</code>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
