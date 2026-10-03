import type { FoundServer, FoundSkill, RepositoryContents } from "./api/types";

/** The assistant's own plugins (src/assistant/core/repositories/known.py), where the sidebar's + installs from. */
export const EXTRAS = "https://github.com/lo9i/lo9i-assistant-extras";

/** A plugin a repository offers: an MCP server (maybe with its skill and a page) or a skill of its own. */
export type Plugin =
  | { kind: "server"; name: string; repository: string; installed: boolean; server: FoundServer }
  | { kind: "skill"; name: string; repository: string; installed: boolean; skill: FoundSkill };

/** Every repository's plugins, in one list. */
export function pluginsOf(byRepository: { url: string; contents: RepositoryContents }[]): Plugin[] {
  return byRepository.flatMap(({ url, contents }) => [
    ...contents.servers.map((server): Plugin => ({ kind: "server", name: server.name, repository: url, installed: server.installed ?? false, server })),
    ...contents.skills.map((skill): Plugin => ({ kind: "skill", name: skill.name, repository: url, installed: skill.installed ?? false, skill })),
  ]);
}

/** "MCP server · skill · page", or "Skill". */
export function kindOf(p: Plugin): string {
  if (p.kind === "skill") return "Skill";
  return ["MCP server", ...(p.server.skill ? ["skill"] : []), ...(p.server.page ? ["page"] : [])].join(" · ");
}

export function describe(p: Plugin): string {
  return p.kind === "server" ? p.server.description : p.skill.description;
}

/** "lo9i/lo9i-assistant-extras" for a GitHub address; the address otherwise. */
export function shortRepository(url: string): string {
  const github = url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+?)(\.git)?\/?$/);
  return github ? github[1] : url.replace(/^https:\/\//, "");
}

/** A plugin's key in the list: the same name can come from two repositories. */
export function keyOf(p: Plugin): string {
  return `${p.repository}#${p.kind}:${p.name}`;
}
