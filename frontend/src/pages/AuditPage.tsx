import { useEffect, useState } from "react";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

interface Row {
  id: number;
  actor: string;
  action: string;
  entity: string;
  entity_id: string | null;
  before: string | null;
  after: string | null;
  created_at: string;
}

export default function AuditPage() {
  const [rows, setRows] = useState<Row[]>([]);

  useEffect(() => {
    api.GET("/api/audit").then(({ data }) => {
      if (data) setRows(data as Row[]);
    });
  }, []);

  return (
    <div>
      <h2>Audit trail</h2>
      <p className="muted">
        Append-only log written by the shared audit helper. Admins see all
        entries; reviewers see their own.
      </p>
      <DataTable<Row>
        columns={[
          { key: "created_at", label: "When" },
          { key: "actor", label: "Who" },
          { key: "action", label: "Action" },
          { key: "entity", label: "Entity" },
          { key: "entity_id", label: "Entity ID" },
          {
            key: "before",
            label: "Before → After",
            sortable: false,
            render: (r) => (
              <code className="diff">
                {r.before ?? "∅"} → {r.after ?? "∅"}
              </code>
            ),
          },
        ]}
        rows={rows}
        filterPlaceholder="Filter audit entries…"
      />
    </div>
  );
}
