/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Backend (FastAPI/WS) origin to proxy to in development. Overridable so the same
// config works against a non-default local backend without editing this file.
const PROXY_TARGET =
  process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Proxy API + WS through Vite in dev so the browser talks to a single origin
    // (the dev server). This sidesteps cross-origin CORS preflights and
    // SameSite/credentialed-cookie issues that a direct localhost:5173 -> :8000
    // call would hit. In prod the app is served same-origin behind the ALB.
    proxy: {
      "/api": {
        target: PROXY_TARGET,
        changeOrigin: true,
        // The backend mounts business routes at /v1 (no /api segment); /api
        // exists only as the browser-side proxy prefix, so strip it here:
        // /api/v1/leaderboard/global -> /v1/leaderboard/global. Prod serving
        // (task 6.9, ALB) must apply the same strip.
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/ws": {
        target: PROXY_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**", "src/vite-env.d.ts"],
    },
  },
});
