// MCP servers' web pages are served by the daemon on the web app's port plus this
// (src/assistant/daemon/pages.py), a different origin, so their scripts can't call the API as the user.
import type { ResolvedTheme } from "./theme.svelte";

export const PAGES_PORT_OFFSET = 1;

type Location = { protocol: string; hostname: string; port: string };

/** The origin pages are served from, seen from the web app at `location`. */
export function pagesOrigin(location: Location): string {
  const port = Number(location.port || (location.protocol === "https:" ? 443 : 80)) + PAGES_PORT_OFFSET;
  const host = location.hostname.includes(":") ? `[${location.hostname}]` : location.hostname;
  return `${location.protocol}//${host}:${port}`;
}

// A place on a page, as the daemon checks a Home item's page_path (src/assistant/core/home/model.py).
const PAGE_PATH = /^[A-Za-z0-9][A-Za-z0-9_\-./]{0,199}$/;

/** Where a server's page is, seen from the web app at `location`, with the app's theme when given: a page can't
 * read the app's, so it's told in its address and, when it changes, by `themeMessage`. `path` is a place on the page
 * (a Home item's `page_path`, like titles/12); one that would leave the page is ignored. */
export function pageUrl(name: string, location: Location, theme?: ResolvedTheme, path = ""): string {
  const query = theme ? `?theme=${theme}` : "";
  const place = PAGE_PATH.test(path) && !path.split("/").includes("..") ? path.split("/").map(encodeURIComponent).join("/") : "";
  return `${pagesOrigin(location)}/${encodeURIComponent(name)}/${place}${query}`;
}

/** The web app's address of a server's page, opened at `path` when given (`pageUrl`). */
export function pageHref(base: string, path = ""): string {
  return path ? `${base}?path=${encodeURIComponent(path)}` : base;
}

/** What the page's frame is sent when the app's theme changes (the extras' pages' theme.js applies it). */
export function themeMessage(theme: ResolvedTheme): { type: "lo9i:theme"; theme: ResolvedTheme } {
  return { type: "lo9i:theme", theme };
}

/** "expenses" → "Expenses", for the sidebar. */
export function pageLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1).replace(/[-_]/g, " ");
}
