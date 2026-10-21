import type { ComponentType } from "react";

/**
 * Generated apps (apps/<name>/frontend/Page.tsx) are discovered at build
 * time. Each page exports `meta` describing where it mounts and which
 * roles may see it — the route guard mirrors the backend's enforcement.
 */
export interface AppMeta {
  title: string;
  path: string;
  description: string;
  roles?: string[];
}

export interface GeneratedApp {
  default: ComponentType;
  meta?: AppMeta;
}

export const generatedApps = import.meta.glob<GeneratedApp>(
  "../../apps/*/frontend/Page.tsx",
  { eager: true }
);

export const appMetas: AppMeta[] = Object.values(generatedApps)
  .map((m) => m.meta)
  .filter((m): m is AppMeta => !!m);
