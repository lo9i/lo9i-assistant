import adapter from "@sveltejs/adapter-static";

// A single-page app: built into the daemon package, which serves it at /app/ and answers every
// path under it with index.html (src/assistant/daemon/web_ui.py).
const config = {
  kit: {
    adapter: adapter({
      pages: "../../src/assistant/daemon/webui",
      assets: "../../src/assistant/daemon/webui",
      fallback: "index.html",
      strict: false,
    }),
    paths: { base: "/app" },
    // Script injected into the page would act as the paired device, so only the app's own files
    // run. SvelteKit puts the hashes of its inline startup script into a <meta> policy.
    csp: {
      mode: "hash",
      directives: {
        "default-src": ["self"],
        "script-src": ["self"],
        "style-src": ["self", "unsafe-inline"],
        "img-src": ["self", "data:", "blob:"],
        "media-src": ["self", "blob:"],
        "connect-src": ["self"],
        "object-src": ["none"],
        "base-uri": ["self"],
        "form-action": ["self"],
      },
    },
  },
};

export default config;
