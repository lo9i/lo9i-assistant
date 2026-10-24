import type { FoundServer, FoundSkill, Offered, PluginIcon, Repository, RepositoryPlugins } from "./api/types";

/** The assistant's extras, official, when a listing's repository isn't named: an empty url installs from them. */
const EXTRAS: Repository = { url: "", name: "the assistant's extras", official: true, private: false };

/** A plugin a repository offers: an MCP server (maybe with its skill, a page or a chat channel), a chat channel, or a skill of its own. */
export type Plugin =
  | { kind: "server"; name: string; installed: boolean; server: FoundServer; repository: Repository }
  | { kind: "skill"; name: string; installed: boolean; skill: FoundSkill; repository: Repository };

export function pluginsOf(contents: Offered, repository: Repository = EXTRAS): Plugin[] {
  return [
    ...contents.servers.map((server): Plugin => ({
      kind: "server",
      name: server.name,
      installed: server.installed ?? false,
      server,
      repository,
    })),
    ...contents.skills.map((skill): Plugin => ({
      kind: "skill",
      name: skill.name,
      installed: skill.installed ?? false,
      skill,
      repository,
    })),
  ];
}

/** Every repository's plugins, the official extras first, and what the ones that couldn't be read said, or the
 *  plugins in them that couldn't be. */
export function fromRepositories(read: RepositoryPlugins[]): { plugins: Plugin[]; errors: string[]; checked: string } {
  return {
    plugins: read.flatMap((r) => (r.contents ? pluginsOf(r.contents, r.repository) : [])),
    errors: [
      ...read.filter((r) => r.error).map((r) => `${r.repository.name}: ${r.error}`),
      ...read.flatMap((r) => (r.contents?.problems ?? []).map((p) => `${r.repository.name}: ${p}`)),
    ],
    checked: lastChecked(read),
  };
}

/** When every repository was last checked: the oldest of their checks, "" while one never was. */
function lastChecked(read: RepositoryPlugins[]): string {
  const times = read.map((r) => r.contents?.checked ?? "");
  return times.includes("") ? "" : times.reduce((a, b) => (a < b ? a : b), times[0] ?? "");
}

/** What the apps show beside it: its own icon, or its category's (src/assistant/core/repositories/icons.py). */
export function iconOf(p: Plugin): PluginIcon | undefined {
  return p.kind === "server" ? p.server.icon : p.skill.icon;
}

/** "Official" for the extras' plugins; the repository's name for the others. */
export function sourceOf(p: Plugin): string {
  return p.repository.official ? "Official" : p.repository.name;
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

/** Whether an installed plugin has a setup to go through: email accounts, or a channel's pairing. */
export function hasSetup(server: FoundServer): boolean {
  return Boolean(server.email || server.channel);
}

/** Where it runs: a remote MCP server runs elsewhere; a local one or a channel on the computer the assistant runs on. */
export function runsOf(server: FoundServer): string {
  return server.transport === "http" ? "Remotely" : "On the assistant's computer";
}

/** A field the daemon already has a value for (from before channels were plugins) may be left empty. */
export function optional(server: FoundServer, key: string): boolean {
  return (server.known_fields ?? []).includes(key) || Boolean(server.fields.find((f) => f.key === key)?.optional);
}

/** What an empty field says: the value saved before stays, or it may be left empty. */
export function emptyHint(server: FoundServer, key: string): string {
  if ((server.known_fields ?? []).includes(key)) return "Leave empty to keep the one already saved";
  return optional(server, key) ? "Optional" : "";
}

/** What an install dialog says about a login of the assistant's the plugin uses instead of its own. */
export function sharedLogin(server: FoundServer): string {
  return server.model_login === "copilot"
    ? "It uses your GitHub Copilot login from Settings → Model while the model is GitHub Copilot."
    : "";
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

/** The extras have a newer version than the one installed: both declare one and they differ. */
export function hasNewer(p: Plugin): boolean {
  const found = p.kind === "server" ? p.server : p.skill;
  return p.installed && Boolean(found.version) && found.version !== (found.installed_version ?? "");
}

export function describe(p: Plugin): string {
  return p.kind === "server" ? p.server.description : p.skill.description;
}

/** What it's for, from the daemon's fixed list: a group and a category in it ("communications/email"). */
export function categoryOf(p: Plugin): string {
  return p.kind === "server" ? p.server.category : p.skill.category;
}

/** The group a category is in: "communications/email" → "communications". */
export function groupOf(category: string): string {
  return category.split("/")[0];
}

/** "communications/email" → "Communications / Email"; a group alone, "communications" → "Communications". */
export function categoryLabel(category: string): string {
  return category
    .split("/")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" / ");
}

/** The plugins grouped by their category's group, in alphabetical order with "other" last, keeping their order within a group. */
export function byCategory(plugins: Plugin[]): Array<{ category: string; plugins: Plugin[] }> {
  const groups = [...new Set(plugins.map((p) => groupOf(categoryOf(p))))].sort(
    (a, b) => Number(a === "other") - Number(b === "other") || a.localeCompare(b),
  );
  return groups.map((group) => ({ category: group, plugins: plugins.filter((p) => groupOf(categoryOf(p)) === group) }));
}

/** A plugin's key in the list: a server and a skill can share a name, and two repositories a plugin's name. */
export function keyOf(p: Plugin): string {
  return `${p.repository.url}|${p.kind}:${p.name}`;
}
