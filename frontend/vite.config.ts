import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // apps/*/frontend import the portal's typed OpenAPI client as @portal/api
    alias: {
      "@portal/api": fileURLToPath(new URL("./src/api/client.ts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // repo root so vite can serve packages/platform/web and apps/*
    fs: { allow: [".."] },
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
