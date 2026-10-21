import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, API_BASE } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Form, FormField } from "../components/Form";

interface SeedUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
}

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState<SeedUser[]>([]);
  const [oidcEnabled, setOidcEnabled] = useState(false);
  const [username, setUsername] = useState("");

  useEffect(() => {
    api.GET("/api/auth/mode").then(({ data }) => {
      if (data && (data as { oidc?: boolean }).oidc) setOidcEnabled(true);
    });
    api.GET("/api/auth/users").then(({ data }) => {
      if (data) {
        setUsers(data as SeedUser[]);
        if (data.length && !username) setUsername(data[0].username);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const selected = users.find((u) => u.username === username);

  return (
    <div className="login-page">
      <Form
        title="Meridian Internal Tools — mock sign in"
        submitLabel={selected ? `Sign in as ${selected.display_name}` : "Sign in"}
        onSubmit={async () => {
          await login(username);
          navigate("/");
        }}
      >
        <p className="muted">
          Proof of concept — no password. Production would use the company SSO.
        </p>
        {oidcEnabled && (
          <button
            type="button"
            className="btn primary"
            onClick={() => {
              window.location.href = `${API_BASE}/api/auth/oidc/login`;
            }}
          >
            Sign in with company SSO
          </button>
        )}
        <FormField label="User">
          <select
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.id} value={u.username}>
                {u.display_name} — {u.role}
              </option>
            ))}
          </select>
        </FormField>
      </Form>
    </div>
  );
}
