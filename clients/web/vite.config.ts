import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

// In development Vite serves /app/ and passes every other path, the API, to the running daemon.
const DAEMON = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [sveltekit()],
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
});
