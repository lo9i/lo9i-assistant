// Turning what the MCP dialogs take as text into what the daemon expects.
import type { McpToolInfo } from "./api/types";

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
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
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

/** A server's status as the page shows it: the daemon's word, with needs_sign_in spelled out. */
export function statusLabel(status: string): string {
  return status === "needs_sign_in" ? "needs you to sign in" : status;
}

export const STATUS_TONES: Record<string, string | undefined> = {
  connected: "var(--color-success)",
  connecting: "var(--color-warn)",
  failed: "var(--color-danger)",
  needs_sign_in: "var(--color-warn)",
  off: undefined,
};
