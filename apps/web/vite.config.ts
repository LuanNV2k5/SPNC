/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// docs/46 D6: same origin. In development the dev server proxies /api (REST and the
// WebSocket) to the API, so the browser never makes a cross-origin request.
const apiTarget = process.env.SPNC_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, ws: true } },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, ws: true } },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 4000 },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["src/test/setup.ts"],
  },
});
