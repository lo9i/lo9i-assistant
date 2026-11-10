// A reply's interactive app (a ```html-app block): a whole HTML document the model wrote, run in a sandboxed frame
// with no network. A srcdoc, data: or blob: frame of the page's would take on the page's own policy, under which no
// inline script runs, so the page frames static/html-app.html, whose policy is APP_POLICY, and sends it the document,
// which it shows in a srcdoc frame of its own under that policy.
import type { ResolvedTheme } from "./theme.svelte";

/** What the frame's document may load: its own inline scripts and styles, and images and fonts in data: or blob:
 * URLs. Nothing it can fetch or frame, not even itself navigated elsewhere, so nothing it holds can be sent anywhere.
 * static/html-app.html declares the same. */
export const APP_POLICY =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; form-action 'none'";
/** Scripts only: never allow-same-origin, which would give it the app's origin, nor forms, popups or the top page. */
export const APP_SANDBOX = "allow-scripts";
export const APP_FRAME = "/html-app.html";
export const DEFAULT_HEIGHT = 320;
const MIN_HEIGHT = 60;
const MAX_HEIGHT = 900;

// Runs before the app's own document, telling the parent how tall it is each time that changes.
const REPORT_HEIGHT =
  "(()=>{const r=()=>parent.postMessage({lo9iAppHeight:Math.ceil(document.documentElement.getBoundingClientRect().height)},'*');" +
  "new ResizeObserver(r).observe(document.documentElement);addEventListener('load',r)})()";

/** The document the frame shows: the policy, the app's theme (so the frame stays clear over the reply and its
 * default text reads), the height report, then the app as written. Whatever the app holds can only add to it: a
 * policy of its own only narrows, and its doctype and <html> fold into the document already started. */
export function appDocument(source: string, theme: ResolvedTheme): string {
  return (
    `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${APP_POLICY}">` +
    `<style>:root{color-scheme:${theme}}</style><script>${REPORT_HEIGHT}</script>` +
    source
  );
}

/** The height a frame's message reports, kept within bounds; null for any other message. */
export function appHeight(data: unknown): number | null {
  if (typeof data !== "object" || data === null || !("lo9iAppHeight" in data)) return null;
  const height = data.lo9iAppHeight;
  if (typeof height !== "number" || !Number.isFinite(height)) return null;
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(height)));
}
