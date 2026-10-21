import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

interface KycCase {
  id: number;
  applicant_name: string;
  country: string;
  status: string;
  risk_score: number;
  risk_level: string;
  assignee: string | null;
  created_at: string;
  sla_breached: boolean;
  approvals: string[];
  approvals_required: number;
}

const STATUSES = ["", "open", "approved", "rejected", "escalated"];
const RISK_BANDS: { label: string; min?: number; max?: number }[] = [
  { label: "All risk" },
  { label: "High (≥70)", min: 70 },
  { label: "Medium (40–69)", min: 40, max: 69 },
  { label: "Low (<40)", max: 39 },
];

export default function KycQueuePage() {
  const [rows, setRows] = useState<KycCase[]>([]);
  const [status, setStatus] = useState("");
  const [band, setBand] = useState(0);

  useEffect(() => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const b = RISK_BANDS[band];
    if (b.min !== undefined) params.set("min_risk", String(b.min));
    if (b.max !== undefined) params.set("max_risk", String(b.max));
    api.GET("/api/kyc/cases", { params: { query: Object.fromEntries(params) } }).then(
      ({ data }) => {
        if (data) setRows(data as unknown as KycCase[]);
      },
    );
  }, [status, band]);

  const breached = useMemo(() => rows.filter((r) => r.sla_breached).length, [rows]);

  return (
    <div>
      <h2>KYC review queue</h2>
      <p className="muted">
        {breached > 0 && (
          <span className="sla-warn">{breached} case(s) past the 48h SLA. </span>
        )}
        Sorted by SLA breach, then risk.
      </p>
      <div className="filters">
        <select className="input filter" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "All statuses"}
            </option>
          ))}
        </select>
        <select className="input filter" value={band} onChange={(e) => setBand(Number(e.target.value))}>
          {RISK_BANDS.map((b, i) => (
            <option key={i} value={i}>
              {b.label}
            </option>
          ))}
        </select>
      </div>
      <DataTable<KycCase>
        columns={[
          {
            key: "id",
            label: "Case",
            render: (r) => <Link to={`/kyc/${r.id}`}>#{r.id}</Link>,
            value: (r) => r.id,
          },
          { key: "applicant_name", label: "Applicant" },
          { key: "country", label: "Country" },
          {
            key: "risk_score",
            label: "Risk",
            render: (r) => (
              <span className={`risk-badge risk-${r.risk_level}`}>
                {r.risk_score} {r.risk_level}
              </span>
            ),
          },
          {
            key: "status",
            label: "Status",
            render: (r) => (
              <span className={`status-badge status-${r.status}`}>{r.status}</span>
            ),
          },
          { key: "assignee", label: "Assignee", value: (r) => r.assignee ?? "—" },
          {
            key: "approvals",
            label: "Approvals",
            sortable: false,
            render: (r) => `${r.approvals.length}/${r.approvals_required}`,
          },
          { key: "created_at", label: "Opened" },
          {
            key: "sla_breached",
            label: "SLA",
            render: (r) => (r.sla_breached ? <span className="sla-warn">BREACHED</span> : "—"),
          },
        ]}
        rows={rows}
        rowClassName={(r) => (r.sla_breached ? "row-sla" : "")}
        filterPlaceholder="Filter cases…"
        filterValue={(r) => `${r.id} ${r.applicant_name} ${r.country} ${r.status} ${r.assignee ?? ""}`}
      />
    </div>
  );
}
