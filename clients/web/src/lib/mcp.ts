// Turning what the MCP dialogs take as text into what the daemon expects.
import type { McpServerStatus, McpToolInfo } from "./api/types";

/** `KEY=value` lines (env) or `Name: value` lines (headers) as a map. Blank lines are skipped.
 * Throws an Error naming the first line without the separator. */
export function parsePairs(text: string, separator: "=" | ":"): Record<string, string> {
  const pairs: Record<string, string> = {};
  for (const line of text.split("\n").map((l) => l.trim())) {
    if (!line) continue;
    const at = line.indexOf(separator);
    if (at <= 0) throw new Error(`"${line}" needs a name, ${separator === "=" ? "=" : ":"} and a value.`);
    pairs[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return pairs;
}

/** Arguments one per line; a single line is split on spaces. */
export function parseArgs(text: string): string[] {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  return lines.length === 1 ? lines[0].split(/\s+/) : lines;
}

export type Selection = { include: string[]; exclude: string[] };

/** The server's tool filter for the chosen tools. All chosen: no filter, so tools the server adds
 * later are used too. None chosen: everything excluded. */
export function selectionFor(tools: McpToolInfo[], chosen: Set<string>): Selection {
  const names = tools.filter((t) => chosen.has(t.name)).map((t) => t.name);
  if (names.length === tools.length) return { include: [], exclude: [] };
  if (names.length === 0) return { include: [], exclude: ["*"] };
  return { include: names, exclude: [] };
}

/** The servers the MCP servers page lists: a plugin without tools (a chat channel, an email provider) is
 *  set up in Plugins. Slack has tools as well as its channel, so it stays. */
export function withTools(servers: McpServerStatus[]): McpServerStatus[] {
  return servers.filter((s) => s.transport !== "none");
}

/** What trusting the server means for its tools: a trusted server's tools run without asking, but those its
 *  plugin says ask first (core/mcp/servers.py's `approve`). */
export function trustText(server: McpServerStatus): string {
  if (!server.trusted) return "Every tool not marked read-only asks for approval first.";
  if (server.tools.some((t) => t.asks_first)) return "Its tools run without asking, but those marked asks first.";
  return "Its tools run without asking.";
}

const LABELS: Record<string, string> = {
  needs_sign_in: "needs you to sign in",
  // A local server stopped until the agent uses it (core/mcp/on_demand.py).
  idle: "starts when used",
};

/** A server's status as the page shows it: the daemon's word, or what it means when that's unclear. */
export function statusLabel(status: string): string {
  return LABELS[status] ?? status;
}

export const STATUS_TONES: Record<string, string | undefined> = {
  connected: "var(--color-success)",
  connecting: "var(--color-warn)",
  failed: "var(--color-danger)",
  needs_sign_in: "var(--color-warn)",
  idle: "var(--color-success)",
  off: undefined,
};
