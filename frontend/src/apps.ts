import type { ComponentType } from "react";

/**
 * Apps (apps/<name>/frontend/Page.tsx) are discovered at build time. Each
 * page exports `meta`: where it mounts (`path` and `path/*`) and which
 * roles the route guard admits — mirroring the backend's enforcement.
 * Home-page cards come from the backend tool registry (/api/tools).
 */
export interface AppMeta {
  path: string;
  roles?: string[];
}

export interface AppModule {
  default: ComponentType;
  meta?: AppMeta;
}

export const apps = import.meta.glob<AppModule>(
  "../../apps/*/frontend/Page.tsx",
  { eager: true }
);
