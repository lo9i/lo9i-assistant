import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

// In development Vite serves /app/ and passes every other path, the API, to the running daemon.
const DAEMON = "http://127.0.0.1:8765";

export default defineConfig(({ mode }) => ({
  plugins: [sveltekit()],
  // Svelte's browser build in the tests, so effects and their teardowns run as on a page; its server build runs none.
  resolve: mode === "test" ? { conditions: ["browser"] } : undefined,
  build: {
    // The time goes in SvelteKit's own plugins, so the report that says so has nothing to act on.
    rolldownOptions: { checks: { pluginTimings: false } },
  },
  server: {
    proxy: {
      "^/(?!app(/|$)).*": { target: DAEMON, changeOrigin: true },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    // Text in English, whatever the computer's language, as the tests expect it.
    setupFiles: ["src/lib/locales/english.ts"],
  },
}));
