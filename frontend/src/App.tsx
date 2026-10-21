import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import AppShell from "./components/AppShell";
import { RequireAuth, RequireRole } from "./components/RequireAuth";
import AuditPage from "./pages/AuditPage";
import DirectoryPage from "./pages/DirectoryPage";
import FlagsPage from "./pages/FlagsPage";
import HomePage from "./pages/HomePage";
import KycCasePage from "./pages/KycCasePage";
import KycQueuePage from "./pages/KycQueuePage";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import RefundsPage from "./pages/RefundsPage";

export default function App() {
  return (
    <AuthProvider>
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
                <RequireRole roles={["reviewer", "admin"]}>
                  <KycQueuePage />
                </RequireRole>
              }
            />
            <Route
              path="/kyc/:id"
              element={
                <RequireRole roles={["reviewer", "admin"]}>
                  <KycCasePage />
                </RequireRole>
              }
            />
            <Route
              path="/refunds"
              element={
                <RequireRole roles={["reviewer", "admin"]}>
                  <RefundsPage />
                </RequireRole>
              }
            />
            <Route
              path="/flags"
              element={
                <RequireRole roles={["reviewer", "admin"]}>
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
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
