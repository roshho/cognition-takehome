import { useEffect, useState } from "react";
import { DataTable, Form, FormField, untypedApi, useAuth } from "@portal/platform";

/**
 * Mounted automatically at `path` (and `path/*`) — see AGENTS.md. `roles`
 * mirrors the backend grants in backend/router.py; the backend enforces
 * regardless. The home-page card comes from register_tool() in router.py.
 */
export const meta = {
  path: "/apps/it-assets",
  description: "Generated internal app — edit me.",
  roles: ["reviewer", "admin", "read_only"],
};

interface Item {
  id: number;
  name: string;
  status: string;
  owner: string | null;
  created_at: string;
}

export default function Page() {
  const { user } = useAuth();
  // Mirror of { it-assets.write } grants in backend/router.py.
  const canWrite = user?.role === "admin" || user?.role === "reviewer";
  const [items, setItems] = useState<Item[]>([]);
  const [name, setName] = useState("");

  const load = async () => {
    const { data } = await untypedApi.GET("/api/it-assets/items", {});
    setItems((data as Item[]) ?? []);
  };

  useEffect(() => {
    void load();
  }, []);

  const create = async () => {
    await untypedApi.POST("/api/it-assets/items", { body: { name } });
    setName("");
    await load();
  };

  const close = async (id: number) => {
    await untypedApi.POST(`/api/it-assets/items/${id}/close`, {});
    await load();
  };

  return (
    <div>
      <h2>It Assets</h2>
      <p className="muted">{meta.description}</p>

      {canWrite && (
        <Form title="New item" submitLabel="Create" onSubmit={create}>
          <FormField label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </FormField>
        </Form>
      )}

      <DataTable<Item>
        columns={[
          { key: "id", label: "ID", sortable: true },
          { key: "name", label: "Name", sortable: true },
          { key: "status", label: "Status", sortable: true },
          { key: "owner", label: "Owner" },
          { key: "created_at", label: "Created", sortable: true },
          ...(canWrite
            ? [
                {
                  key: "_actions",
                  label: "",
                  render: (row: Item) =>
                    row.status === "open" ? (
                      <button className="link-btn" onClick={() => close(row.id)}>
                        Close
                      </button>
                    ) : null,
                },
              ]
            : []),
        ]}
        rows={items}
        filterValue={(row) => `${row.name} ${row.status} ${row.owner ?? ""}`}
        emptyMessage="No items yet."
      />
    </div>
  );
}
