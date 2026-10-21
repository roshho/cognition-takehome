import { useEffect, useState } from "react";
import { api } from "../api/client";
import DataTable from "../components/DataTable";

interface Row {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

export default function DirectoryPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.GET("/api/users").then(({ data, error }) => {
      if (error) setError("Could not load users (403 means your role lacks access).");
      else if (data) setRows(data as Row[]);
    });
  }, []);

  if (error) return <div className="card"><p className="form-error">{error}</p></div>;

  return (
    <div>
      <h2>User directory</h2>
      <DataTable<Row>
        columns={[
          { key: "username", label: "Username" },
          { key: "display_name", label: "Name" },
          {
            key: "role",
            label: "Role",
            render: (r) => <span className={`role-badge role-${r.role}`}>{r.role}</span>,
          },
        ]}
        rows={rows}
        filterPlaceholder="Filter users…"
      />
    </div>
  );
}
