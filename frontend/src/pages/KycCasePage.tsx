import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface KycCaseDetail {
  id: number;
  applicant_name: string;
  dob: string;
  email: string;
  phone: string;
  address: string;
  national_id: string;
  country: string;
  status: string;
  risk_score: number;
  risk_level: string;
  assignee: string | null;
  created_at: string;
  decided_at: string | null;
  sla_breached: boolean;
  approvals: string[];
  approvals_required: number;
  documents: { id: number; doc_type: string; filename: string }[];
  hits: { id: number; hit_type: string; match_name: string; score: number; summary: string }[];
  notes: { id: number; author: string; body: string; created_at: string }[];
}

interface Pii {
  dob: string;
  email: string;
  phone: string;
  address: string;
  national_id: string;
}

export default function KycCasePage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [c, setCase] = useState<KycCaseDetail | null>(null);
  const [pii, setPii] = useState<Pii | null>(null);
  const [reasonCodes, setReasonCodes] = useState<{ reject: string[]; escalate: string[] } | null>(null);
  const [action, setAction] = useState<"reject" | "escalate" | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { data } = await api.GET("/api/kyc/cases/{case_id}", {
      params: { path: { case_id: Number(id) } },
    });
    if (data) setCase(data as unknown as KycCaseDetail);
  }, [id]);

  useEffect(() => {
    void load();
    api.GET("/api/kyc/reason-codes").then(({ data }) => {
      if (data) setReasonCodes(data as { reject: string[]; escalate: string[] });
    });
  }, [load]);

  if (!c) return <p className="muted">Loading…</p>;

  const isOpen = c.status === "open";
  const alreadyApproved = user ? c.approvals.includes(user.username) : false;
  const needsSecond = c.approvals_required > c.approvals.length;

  const doAction = async (
    action: "assign" | "approve" | "reject" | "escalate",
    body: { reason_code: string } = { reason_code: "" },
  ) => {
    setError(null);
    setMessage(null);
    const params = { path: { case_id: c.id } };
    const result =
      action === "assign"
        ? await api.POST("/api/kyc/cases/{case_id}/assign", { params })
        : action === "approve"
          ? await api.POST("/api/kyc/cases/{case_id}/approve", { params })
          : action === "reject"
            ? await api.POST("/api/kyc/cases/{case_id}/reject", { params, body })
            : await api.POST("/api/kyc/cases/{case_id}/escalate", { params, body });
    const { data, error } = result;
    if (error) {
      const detail = (error as { detail?: string }).detail;
      setError(detail ?? "Action failed");
      return;
    }
    if (action === "approve" && (data as { awaiting_second_reviewer?: boolean }).awaiting_second_reviewer) {
      setMessage("Approval recorded — awaiting a second reviewer (four-eyes).");
    }
    setAction(null);
    setReason("");
    await load();
  };

  const unmask = async () => {
    const { data, error } = await api.POST("/api/kyc/cases/{case_id}/unmask", {
      params: { path: { case_id: c.id } },
    });
    if (!error && data) setPii(data as Pii);
  };

  const addNote = async () => {
    setError(null);
    const { error } = await api.POST("/api/kyc/cases/{case_id}/notes", {
      params: { path: { case_id: c.id } },
      body: { body: note },
    });
    if (error) {
      setError("Could not add note");
      return;
    }
    setNote("");
    await load();
  };

  const piiRows: [string, string][] = [
    ["Date of birth", pii?.dob ?? c.dob],
    ["Email", pii?.email ?? c.email],
    ["Phone", pii?.phone ?? c.phone],
    ["Address", pii?.address ?? c.address],
    ["National ID", pii?.national_id ?? c.national_id],
  ];

  return (
    <div>
      <p><Link to="/kyc">← Queue</Link></p>
      <div className="case-header">
        <h2>
          #{c.id} — {c.applicant_name}
        </h2>
        <span className={`status-badge status-${c.status}`}>{c.status}</span>
        <span className={`risk-badge risk-${c.risk_level}`}>
          risk {c.risk_score} ({c.risk_level})
        </span>
        {c.sla_breached && <span className="sla-warn">SLA breached (&gt;48h)</span>}
      </div>

      <div className="case-grid">
        <section className="card">
          <h3>Applicant</h3>
          <table className="kv">
            <tbody>
              <tr><td>Country</td><td>{c.country}</td></tr>
              {piiRows.map(([k, v]) => (
                <tr key={k}><td>{k}</td><td><code>{v}</code></td></tr>
              ))}
            </tbody>
          </table>
          {!pii && user?.role !== "read_only" ? (
            <button className="btn" onClick={unmask}>
              Reveal PII <span className="muted">(audited)</span>
            </button>
          ) : user?.role === "read_only" ? (
            <p className="muted">PII reveal is not available for read-only accounts.</p>
          ) : (
            <p className="muted">PII revealed — this was written to the audit log.</p>
          )}
        </section>

        <section className="card">
          <h3>Screening</h3>
          {c.hits.length === 0 && <p className="muted">No sanctions or PEP hits.</p>}
          {c.hits.map((h) => (
            <div key={h.id} className="hit">
              <span className={`hit-badge hit-${h.hit_type}`}>{h.hit_type.toUpperCase()}</span>{" "}
              <strong>{h.match_name}</strong> — score {h.score}
              <p className="muted">{h.summary}</p>
            </div>
          ))}
          <h3>Documents</h3>
          <ul className="doc-list">
            {c.documents.map((d) => (
              <li key={d.id}>
                <code>{d.filename}</code> <span className="muted">({d.doc_type}, placeholder)</span>
              </li>
            ))}
          </ul>
          <h3>Decisions</h3>
          <p className="muted">
            Approvals: {c.approvals.length}/{c.approvals_required}
            {c.approvals.length > 0 && ` (${c.approvals.join(", ")})`}
            {c.decided_at && ` — decided ${c.decided_at}`}
          </p>
        </section>
      </div>

      {isOpen && user?.role !== "read_only" && (
        <section className="card actions">
          <h3>Actions</h3>
          {error && <p className="form-error">{error}</p>}
          {message && <p className="form-ok">{message}</p>}
          <div className="action-row">
            <button className="btn" onClick={() => doAction("assign")} disabled={c.assignee === user?.username}>
              {c.assignee === user?.username ? "Assigned to you" : "Assign to me"}
            </button>
            <button
              className="btn primary"
              onClick={() => doAction("approve")}
              disabled={alreadyApproved}
              title={
                alreadyApproved
                  ? "You already approved — a second reviewer is required"
                  : needsSecond
                    ? `Requires ${c.approvals_required} approvers`
                    : "Approve"
              }
            >
              {needsSecond && c.approvals_required === 2
                ? `Approve (${c.approvals.length}/2)`
                : "Approve"}
            </button>
            <button className="btn" onClick={() => { setAction("reject"); setReason(""); }}>
              Reject
            </button>
            <button className="btn" onClick={() => { setAction("escalate"); setReason(""); }}>
              Escalate
            </button>
          </div>
          {action && reasonCodes && (
            <div className="reason-box">
              <label className="form-label">Reason code ({action})</label>
              <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
                <option value="">Select a reason…</option>
                {reasonCodes[action].map((rc) => (
                  <option key={rc} value={rc}>{rc}</option>
                ))}
              </select>
              <div className="action-row">
                <button
                  className="btn primary"
                  disabled={!reason}
                  onClick={() => doAction(action, { reason_code: reason })}
                >
                  Confirm {action}
                </button>
                <button className="btn" onClick={() => setAction(null)}>Cancel</button>
              </div>
            </div>
          )}
        </section>
      )}

      <section className="card">
        <h3>Notes</h3>
        {c.notes.map((n) => (
          <p key={n.id} className="note">
            <strong>{n.author}</strong> <span className="muted">{n.created_at}</span>
            <br />
            {n.body}
          </p>
        ))}
        {user?.role !== "read_only" && (
        <div className="note-add">
          <input
            className="input"
            placeholder="Add a note…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button className="btn" onClick={addNote} disabled={!note.trim()}>
            Add note
          </button>
        </div>
        )}
      </section>
    </div>
  );
}
