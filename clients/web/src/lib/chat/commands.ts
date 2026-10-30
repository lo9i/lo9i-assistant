// The web UI's slash commands, like clients/terminal/src/assistant_terminal/commands.py. The terminal's /mouse
// and /quit have no meaning in a browser; /settings opens the settings page.

import type { Agent } from "$lib/api/types";
import { t, type Key, type Values } from "$lib/i18n.svelte";

/** `description` is a text's key, shown with `values` (commandText). */
export type Command = { name: string; usage: string; description: Key; values?: Values };

export const COMMANDS: Command[] = [
  { name: "/clear", usage: "/clear", description: "commands.clear" },
  { name: "/conversations", usage: "/conversations", description: "commands.conversations" },
  { name: "/move", usage: "/move", description: "commands.move" },
  { name: "/notifications", usage: "/notifications", description: "commands.notifications" },
  { name: "/attach", usage: "/attach", description: "commands.attach" },
  { name: "/sessions", usage: "/sessions", description: "commands.sessions" },
  { name: "/jobs", usage: "/jobs", description: "commands.jobs" },
  { name: "/settings", usage: "/settings", description: "commands.settings" },
  { name: "/mcp", usage: "/mcp", description: "commands.mcp" },
  { name: "/plugins", usage: "/plugins", description: "commands.plugins" },
  { name: "/skills", usage: "/skills", description: "commands.skills" },
  { name: "/import-skills", usage: "/import-skills", description: "commands.importSkills" },
  { name: "/usage", usage: "/usage", description: "commands.usage" },
  { name: "/audio", usage: "/audio", description: "commands.audio" },
  { name: "/websearch", usage: "/websearch", description: "commands.websearch" },
  { name: "/startup", usage: "/startup", description: "commands.startup" },
  { name: "/name", usage: "/name <name>", description: "commands.name" },
  { name: "/pin", usage: "/pin <skill>", description: "commands.pin" },
  { name: "/unpin", usage: "/unpin <skill>", description: "commands.unpin" },
  { name: "/profile", usage: "/profile", description: "commands.profile" },
  { name: "/get-to-know-me", usage: "/get-to-know-me", description: "commands.getToKnowMe" },
  { name: "/help", usage: "/help", description: "commands.help" },
];

/** What a command does, in the language shown. */
export function commandText(command: Command): string {
  return t(command.description, command.values);
}

export function takesArgument(command: Command): boolean {
  return command.usage !== command.name;
}

/** The commands installed plugins' agents add (/claude), leaving out any that would hide a built-in one. */
export function agentCommands(agents: Agent[]): Command[] {
  return agents
    .filter((a) => !known(`/${a.command}`))
    .map((a) => ({
      name: `/${a.command}`,
      usage: `/${a.command} [folder] | off`,
      description: "commands.agent",
      values: { agent: a.name },
    }));
}

/** Commands to offer while the command name is being typed: text starting with / and no space yet. */
export function offered(text: string, extra: Command[] = []): Command[] {
  if (!text.startsWith("/") || /\s/.test(text) || text.indexOf("/", 1) >= 0) return [];
  return [...COMMANDS, ...extra].filter((c) => c.name.startsWith(text));
}

/** A typed command line, split into the command and its argument; null for a message. */
export function parse(text: string): { name: string; arg: string } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const space = trimmed.search(/\s/);
  const name = space < 0 ? trimmed : trimmed.slice(0, space);
  // A path like /Users/me/project is a message, not a command: names have no second slash.
  if (name.indexOf("/", 1) >= 0) return null;
  return { name, arg: space < 0 ? "" : trimmed.slice(space).trim() };
}

export function known(name: string): boolean {
  return COMMANDS.some((c) => c.name === name);
}

/** What /get-to-know-me and the Settings button send: the get-to-know-you skill starts from it. */
export const GET_TO_KNOW_ME = "Get to know me.";
