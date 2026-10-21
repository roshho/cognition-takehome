import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // repo root so vite can serve packages/platform/web and apps/*
    fs: { allow: [".."] },
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
