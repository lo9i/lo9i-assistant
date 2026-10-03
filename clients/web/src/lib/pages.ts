// MCP servers' web pages are served by the daemon on the web app's port plus this
// (src/assistant/daemon/pages.py), a different origin, so their scripts can't call the API as the user.
export const PAGES_PORT_OFFSET = 1;

/** Where a server's page is, seen from the web app at `location`. */
export function pageUrl(name: string, location: { protocol: string; hostname: string; port: string }): string {
  const port = Number(location.port || (location.protocol === "https:" ? 443 : 80)) + PAGES_PORT_OFFSET;
  const host = location.hostname.includes(":") ? `[${location.hostname}]` : location.hostname;
  return `${location.protocol}//${host}:${port}/${encodeURIComponent(name)}/`;
}

/** "expenses" → "Expenses", for the sidebar. */
export function pageLabel(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1).replace(/[-_]/g, " ");
}
