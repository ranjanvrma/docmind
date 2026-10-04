/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The FastAPI backend serves the API under /api. In development, Vite proxies
// /api to it, so the browser always talks to a single origin (no CORS).
const apiTarget = process.env.DOCMIND_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // The 3D scene chunk (three.js, ~240 kB gzipped) is lazy-loaded on the home page only.
    chunkSizeWarningLimit: 1000,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
