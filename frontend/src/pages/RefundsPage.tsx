import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "@portal/platform";
import { DataTable } from "@portal/platform";

interface Refund {
  id: number;
  customer_name: string;
  customer_email: string;
  amount_cents: number;
  currency: string;
  reason: string;
  status: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  requires_admin: boolean;
}

interface Stats {
  pending_count: number;
  pending_amount_cents: number;
  approved_count: number;
  approved_amount_cents: number;
  denied_count: number;
  denied_amount_cents: number;
  admin_threshold_cents: number;
}

const STATUSES = ["", "pending", "approved", "denied"];

const money = (cents: number, currency = "USD") =>
  `${(cents / 100).toLocaleString("en-US", { style: "currency", currency })}`;

export default function RefundsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<Refund[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [status, setStatus] = useState("");
  const [minAmt, setMinAmt] = useState("");
  const [maxAmt, setMaxAmt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const q: Record<string, string> = {};
    if (status) q.status = status;
    if (minAmt) q.min_amount = String(Math.round(Number(minAmt) * 100));
    if (maxAmt) q.max_amount = String(Math.round(Number(maxAmt) * 100));
    const [{ data: refunds }, { data: s }] = await Promise.all([
      api.GET("/api/refunds", { params: { query: q } }),
      api.GET("/api/refunds/stats"),
    ]);
    if (refunds) setRows(refunds as Refund[]);
    if (s) setStats(s as Stats);
  }, [status, minAmt, maxAmt]);

  useEffect(() => {
    void load();
  }, [load]);

  const decide = async (id: number, action: "approve" | "deny") => {
    setError(null);
    const { error } =
      action === "approve"
        ? await api.POST("/api/refunds/{refund_id}/approve", {
            params: { path: { refund_id: id } },
            body: {},
          })
        : await api.POST("/api/refunds/{refund_id}/deny", {
            params: { path: { refund_id: id } },
            body: {},
          });
    if (error) {
      const detail = (error as { detail?: string }).detail;
      setError(detail ?? "Action failed");
      return;
    }
    await load();
  };

  return (
    <div>
      <h2>Refunds</h2>
      {stats && (
        <div className="stats-row">
          <div className="card stat">
            <span className="stat-num">{stats.pending_count}</span>
            <span className="muted">
              pending — {money(stats.pending_amount_cents)}
            </span>
          </div>
          <div className="card stat">
            <span className="stat-num">{stats.approved_count}</span>
            <span className="muted">
              approved — {money(stats.approved_amount_cents)}
            </span>
          </div>
          <div className="card stat">
            <span className="stat-num">{stats.denied_count}</span>
            <span className="muted">
              denied — {money(stats.denied_amount_cents)}
            </span>
          </div>
          <div className="card stat">
            <span className="stat-num">
              {money(stats.admin_threshold_cents)}+
            </span>
            <span className="muted">requires admin</span>
          </div>
        </div>
      )}
      {error && <p className="form-error">{error}</p>}
      <div className="filters">
        <select className="input filter" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s || "All statuses"}</option>
          ))}
        </select>
        <input
          className="input filter"
          type="number"
          min="0"
          placeholder="Min $"
          value={minAmt}
          onChange={(e) => setMinAmt(e.target.value)}
        />
        <input
          className="input filter"
          type="number"
          min="0"
          placeholder="Max $"
          value={maxAmt}
          onChange={(e) => setMaxAmt(e.target.value)}
        />
      </div>
      <DataTable<Refund>
        columns={[
          { key: "id", label: "#", value: (r) => r.id },
          { key: "customer_name", label: "Customer" },
          {
            key: "amount_cents",
            label: "Amount",
            render: (r) => (
              <span>
                {money(r.amount_cents, r.currency)}
                {r.requires_admin && (
                  <span className="admin-flag" title="Requires admin"> admin</span>
                )}
              </span>
            ),
            value: (r) => r.amount_cents,
          },
          { key: "reason", label: "Reason" },
          {
            key: "status",
            label: "Status",
            render: (r) => (
              <span className={`status-badge status-${r.status}`}>{r.status}</span>
            ),
          },
          {
            key: "decided_by",
            label: "Decided by",
            sortable: false,
            render: (r) => (r.decided_by ? `${r.decided_by} (${r.decided_at})` : "—"),
          },
          { key: "created_at", label: "Requested" },
          {
            key: "actions",
            label: "Actions",
            sortable: false,
            render: (r) =>
              r.status !== "pending" ? (
                <span className="muted">closed</span>
              ) : (
                <span className="action-cell">
                  <button
                    className="btn small"
                    disabled={(r.requires_admin && user?.role !== "admin") || user?.role === "read_only"}
                    title={
                      r.requires_admin && user?.role !== "admin"
                        ? "Requires an admin"
                        : "Approve"
                    }
                    onClick={() => decide(r.id, "approve")}
                  >
                    Approve
                  </button>
                  <button
                    className="btn small"
                    disabled={(r.requires_admin && user?.role !== "admin") || user?.role === "read_only"}
                    onClick={() => decide(r.id, "deny")}
                  >
                    Deny
                  </button>
                </span>
              ),
          },
        ]}
        rows={rows}
        filterPlaceholder="Filter refunds…"
        filterValue={(r) =>
          `${r.id} ${r.customer_name} ${r.customer_email} ${r.reason} ${r.status}`
        }
      />
    </div>
  );
}
