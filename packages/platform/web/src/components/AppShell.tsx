import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export interface ShellLink {
  to: string;
  label: string;
}

export default function AppShell({
  brand = "Meridian Internal Tools",
  links = [
    { to: "/", label: "Home" },
    { to: "/profile", label: "Profile" },
  ],
}: {
  brand?: string;
  links?: ShellLink[];
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [brandLead, ...brandRest] = brand.split(" ");

  return (
    <div className="shell">
      <header className="shell-header">
        <Link to="/" className="brand">
          {brandLead} <span>{brandRest.join(" ")}</span>
        </Link>
        <nav>
          {links.map((l) => (
            <Link key={l.to} to={l.to}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="shell-user">
          {user && (
            <>
              <span className={`role-badge role-${user.role}`}>{user.role}</span>
              <span>{user.display_name}</span>
              <button
                className="link-btn"
                onClick={async () => {
                  await logout();
                  navigate("/login");
                }}
              >
                Log out
              </button>
            </>
          )}
        </div>
      </header>
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  );
}
