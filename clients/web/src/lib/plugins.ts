import type { FoundServer, FoundSkill, RepositoryContents } from "./api/types";

/** A plugin the assistant's extras offer: an MCP server (maybe with its skill, a page or a chat channel), a chat channel, or a skill of its own. */
export type Plugin =
  | { kind: "server"; name: string; installed: boolean; server: FoundServer }
  | { kind: "skill"; name: string; installed: boolean; skill: FoundSkill };

export function pluginsOf(contents: RepositoryContents): Plugin[] {
  return [
    ...contents.servers.map((server): Plugin => ({ kind: "server", name: server.name, installed: server.installed ?? false, server })),
    ...contents.skills.map((skill): Plugin => ({ kind: "skill", name: skill.name, installed: skill.installed ?? false, skill })),
  ];
}

/** "MCP server · channel · skill · page", "Channel" (a chat channel without tools), "Email provider", or "Skill". */
export function kindOf(p: Plugin): string {
  if (p.kind === "skill") return "Skill";
  const parts: Array<[string, boolean | undefined]> = [
    ["MCP server", p.server.transport !== "none"],
    ["channel", p.server.channel],
    ["email provider", p.server.email],
    ["skill", p.server.skill],
    ["page", p.server.page],
  ];
  const kind = parts
    .filter(([, has]) => has)
    .map(([part]) => part)
    .join(" · ");
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

/** Whether a category has settings its plugins share, shown when its name is picked. */
export function hasSettings(category: string): boolean {
  return category === "communications";
}

/** Where it runs: a remote MCP server runs elsewhere; a local one or a channel on the computer the assistant runs on. */
export function runsOf(server: FoundServer): string {
  return server.transport === "http" ? "Remotely" : "On the assistant's computer";
}

/** A field the daemon already has a value for (from before channels were plugins) may be left empty. */
export function optional(server: FoundServer, key: string): boolean {
  return (server.known_fields ?? []).includes(key);
}

/** The first required field left empty, to say so before installing; null when all are there. */
export function missingField(server: FoundServer, values: Record<string, string>): string | null {
  const field = server.fields.find((f) => !optional(server, f.key) && !(values[f.key] ?? "").trim());
  return field ? field.label : null;
}

/** The version installed, and the newer one the extras have ("1.0.0 → 1.1.0"); what the extras
 *  have when it isn't installed; "–" when none is declared. */
export function versionOf(p: Plugin): string {
  const found = p.kind === "server" ? p.server : p.skill;
  const available = found.version ?? "";
  const here = found.installed_version ?? "";
  if (!p.installed) return available || "–";
  if (available && available !== here) return `${here || "–"} → ${available}`;
  return here || "–";
}

/** Whether Update makes sense: the extras have another version than the one installed. Without a
 *  declared version there's no telling, so it's offered. */
export function updatable(p: Plugin): boolean {
  const found = p.kind === "server" ? p.server : p.skill;
  const available = found.version ?? "";
  return p.installed && (!available || available !== (found.installed_version ?? ""));
}

export function describe(p: Plugin): string {
  return p.kind === "server" ? p.server.description : p.skill.description;
}

/** What it's for, from the daemon's fixed list ("communications", ..., "other"). */
export function categoryOf(p: Plugin): string {
  return p.kind === "server" ? p.server.category : p.skill.category;
}

/** "communications" → "Communications". */
export function categoryLabel(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

/** The plugins grouped by category, in alphabetical order with "other" last, keeping their order within a group. */
export function byCategory(plugins: Plugin[]): Array<{ category: string; plugins: Plugin[] }> {
  const categories = [...new Set(plugins.map(categoryOf))].sort(
    (a, b) => Number(a === "other") - Number(b === "other") || a.localeCompare(b),
  );
  return categories.map((category) => ({ category, plugins: plugins.filter((p) => categoryOf(p) === category) }));
}

/** A plugin's key in the list: a server and a skill can share a name. */
export function keyOf(p: Plugin): string {
  return `${p.kind}:${p.name}`;
}
