import adapter from "@sveltejs/adapter-static";

// A single-page app: built into the daemon package, which serves it at /app/ and answers every
// path under it with index.html (src/lo9i/daemon/web_ui.py).
const config = {
  kit: {
    adapter: adapter({
      pages: "../../src/lo9i/daemon/webui",
      assets: "../../src/lo9i/daemon/webui",
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
        // MCP servers' pages: the daemon on the next port, on localhost or over HTTPS (src/lib/pages.ts); and the
        // replies' apps, run from the page's own html-app.html (src/lib/htmlApp.ts).
        "frame-src": ["self", "http://127.0.0.1:*", "http://localhost:*", "https:"],
        "object-src": ["none"],
        "base-uri": ["self"],
        "form-action": ["self"],
      },
    },
  },
};

export default config;
