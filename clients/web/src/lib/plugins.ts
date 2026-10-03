import type { FoundServer, FoundSkill, RepositoryContents } from "./api/types";

/** A plugin the assistant's extras offer: an MCP server (maybe with its skill and a page) or a skill of its own. */
export type Plugin =
  | { kind: "server"; name: string; installed: boolean; server: FoundServer }
  | { kind: "skill"; name: string; installed: boolean; skill: FoundSkill };

export function pluginsOf(contents: RepositoryContents): Plugin[] {
  return [
    ...contents.servers.map((server): Plugin => ({ kind: "server", name: server.name, installed: server.installed ?? false, server })),
    ...contents.skills.map((skill): Plugin => ({ kind: "skill", name: skill.name, installed: skill.installed ?? false, skill })),
  ];
}

/** "MCP server · skill · page", or "Skill". */
export function kindOf(p: Plugin): string {
  if (p.kind === "skill") return "Skill";
  return ["MCP server", ...(p.server.skill ? ["skill"] : []), ...(p.server.page ? ["page"] : [])].join(" · ");
}

export function describe(p: Plugin): string {
  return p.kind === "server" ? p.server.description : p.skill.description;
}

/** A plugin's key in the list: a server and a skill can share a name. */
export function keyOf(p: Plugin): string {
  return `${p.kind}:${p.name}`;
}
