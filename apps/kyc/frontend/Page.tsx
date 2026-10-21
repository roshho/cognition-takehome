import { Route, Routes } from "react-router-dom";
import CasePage from "./CasePage";
import QueuePage from "./QueuePage";

/** Mounted at /kyc/* — roles mirror the backend grants in backend/router.py. */
export const meta = {
  path: "/kyc",
  roles: ["reviewer", "admin", "read_only"],
};

export default function Page() {
  return (
    <Routes>
      <Route index element={<QueuePage />} />
      <Route path=":id" element={<CasePage />} />
    </Routes>
  );
}
