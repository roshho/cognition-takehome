import createClient from "openapi-fetch";
import type { paths } from "./schema";

const TOKEN_KEY = "portal.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// In dev, "/" is proxied to FastAPI by vite. In the docker image the static
// build points at the API container's published port via VITE_API_URL.
const baseUrl = import.meta.env.VITE_API_URL ?? "/";

export const api = createClient<paths>({
  baseUrl,
  headers: { Accept: "application/json" },
});

api.use({
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
});
