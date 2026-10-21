import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "@portal/platform";
import { Form, FormField } from "@portal/platform";

export default function ProfilePage() {
  const { user, refresh } = useAuth();
  const [name, setName] = useState(user?.display_name ?? "");
  const [saved, setSaved] = useState(false);

  return (
    <div>
      <h2>Profile</h2>
      <p className="muted">
        Renaming yourself is a real mutation — it's written to the audit log.
      </p>
      <Form
        title="Display name"
        onSubmit={async () => {
          const { error } = await api.PATCH("/api/me", {
            body: { display_name: name },
          });
          if (error) throw new Error("Update failed");
          await refresh();
          setSaved(true);
        }}
      >
        <FormField label="Name">
          <input
            className="input"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setSaved(false);
            }}
          />
        </FormField>
        {saved && <p className="form-ok">Saved — check the audit trail.</p>}
      </Form>
    </div>
  );
}
