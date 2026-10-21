import { BrowserRouter, Route, Routes } from "react-router-dom";
import {
  AppShell,
  AuthProvider,
  RequireAuth,
  RequireRole,
} from "@portal/platform";
import { api } from "./api/client";
import { apps } from "./apps";
import AuditPage from "./pages/AuditPage";
import DirectoryPage from "./pages/DirectoryPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";

const ALL_ROLES = ["reviewer", "admin", "read_only"];

export default function App() {
  return (
    <AuthProvider api={api}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="/" element={<HomePage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/audit" element={<AuditPage />} />
            <Route
              path="/directory"
              element={
                <RequireRole roles={["admin"]}>
                  <DirectoryPage />
                </RequireRole>
              }
            />
            {Object.values(apps).map((m) => {
              const Page = m.default;
              const meta = m.meta;
              if (!meta) return null;
              return (
                <Route
                  key={meta.path}
                  path={`${meta.path}/*`}
                  element={
                    <RequireRole roles={meta.roles ?? ALL_ROLES}>
                      <Page />
                    </RequireRole>
                  }
                />
              );
            })}
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
