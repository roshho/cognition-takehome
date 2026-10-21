import { BrowserRouter, Route, Routes } from "react-router-dom";
import {
  AppShell,
  AuthProvider,
  RequireAuth,
  RequireRole,
} from "@portal/platform";
import { api } from "./api/client";
import { generatedApps } from "./apps";
import AuditPage from "./pages/AuditPage";
import DirectoryPage from "./pages/DirectoryPage";
import FlagsPage from "./pages/FlagsPage";
import HomePage from "./pages/HomePage";
import KycCasePage from "./pages/KycCasePage";
import KycQueuePage from "./pages/KycQueuePage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import RefundsPage from "./pages/RefundsPage";

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
              path="/kyc"
              element={
                <RequireRole roles={["reviewer", "admin", "read_only"]}>
                  <KycQueuePage />
                </RequireRole>
              }
            />
            <Route
              path="/kyc/:id"
              element={
                <RequireRole roles={["reviewer", "admin", "read_only"]}>
                  <KycCasePage />
                </RequireRole>
              }
            />
            <Route
              path="/refunds"
              element={
                <RequireRole roles={["reviewer", "admin", "read_only"]}>
                  <RefundsPage />
                </RequireRole>
              }
            />
            <Route
              path="/flags"
              element={
                <RequireRole roles={["reviewer", "admin", "read_only"]}>
                  <FlagsPage />
                </RequireRole>
              }
            />
            <Route
              path="/directory"
              element={
                <RequireRole roles={["admin"]}>
                  <DirectoryPage />
                </RequireRole>
              }
            />
            {Object.values(generatedApps).map((m) => {
              const Page = m.default;
              const meta = m.meta;
              if (!meta) return null;
              return (
                <Route
                  key={meta.path}
                  path={meta.path}
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
