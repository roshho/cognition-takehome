import createClient, { type Client } from "openapi-fetch";

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
export const API_BASE: string = import.meta.env.VITE_API_URL ?? "";

/**
 * Create an API client that injects the session bearer token on every
 * request. Apps with a generated OpenAPI schema pass their `paths` type;
 * generated apps without one use `untypedApi`.
 */
export function createPortalClient<Paths extends object>() {
  const client = createClient<Paths>({
    baseUrl: API_BASE || "/",
    headers: { Accept: "application/json" },
  });
  client.use({
    onRequest({ request }) {
      const token = getToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  });
  return client;
}

/** Untyped client for generated apps — responses are `any`. */
export const untypedApi: Client<any> = createPortalClient<any>();
