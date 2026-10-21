import { createPortalClient } from "@portal/platform";
import type { paths } from "./schema";

// App-local typed client (generated from backend/openapi.json).
// Generated apps under apps/ use @portal/platform's untypedApi instead.
export const api = createPortalClient<paths>();

export { API_BASE, getToken, setToken } from "@portal/platform";
