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

/** "MCP server · channel · skill · page", "Channel" (a chat channel without tools), or "Skill". */
export function kindOf(p: Plugin): string {
  if (p.kind === "skill") return "Skill";
  const onlyChannel = p.server.transport === "channel";
  const parts: Array<[string, boolean | undefined]> = [
    [onlyChannel ? "Channel" : "MCP server", true],
    ["channel", p.server.channel && !onlyChannel],
    ["skill", p.server.skill],
    ["page", p.server.page],
  ];
  return parts
    .filter(([, has]) => has)
    .map(([part]) => part)
    .join(" · ");
}

/** Where it runs: a remote MCP server runs elsewhere; a local one or a channel on this computer. */
export function runsOf(server: FoundServer): string {
  return server.transport === "http" ? "Remotely" : "On this computer";
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

/** A plugin's key in the list: a server and a skill can share a name. */
export function keyOf(p: Plugin): string {
  return `${p.kind}:${p.name}`;
}
