import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="shell">
      <header className="shell-header">
        <Link to="/" className="brand">
          Meridian <span>Internal Tools</span>
        </Link>
        <nav>
          <Link to="/">Home</Link>
          <Link to="/profile">Profile</Link>
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
