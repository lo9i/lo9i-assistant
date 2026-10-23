// The web UI's slash commands, like src/assistant/gateways/cli/commands.py. The terminal's /mouse
// and /quit have no meaning in a browser; /settings opens the settings page.

import type { Agent } from "$lib/api/types";

export type Command = { name: string; usage: string; description: string };

export const COMMANDS: Command[] = [
  { name: "/new", usage: "/new", description: "Start a new conversation" },
  { name: "/conversations", usage: "/conversations", description: "Your conversations, newest first, to open one" },
  { name: "/inbox", usage: "/inbox", description: "Back to the inbox: the next message goes where it belongs" },
  { name: "/move", usage: "/move", description: "Move the last message the inbox sent on to another conversation" },
  { name: "/notifications", usage: "/notifications", description: "Job results and background work that ended" },
  { name: "/attach", usage: "/attach", description: "Attach files to the next message" },
  { name: "/sessions", usage: "/sessions", description: "Clients connected to the daemon" },
  { name: "/jobs", usage: "/jobs", description: "Scheduled jobs" },
  { name: "/settings", usage: "/settings", description: "Name, appearance, model, start at boot, web search and audio" },
  { name: "/mcp", usage: "/mcp", description: "MCP servers and their tools" },
  { name: "/plugins", usage: "/plugins", description: "Install, update and remove plugins from the extras" },
  { name: "/skills", usage: "/skills", description: "Browse, install and delete skills" },
  { name: "/usage", usage: "/usage", description: "Tool and skill usage" },
  { name: "/audio", usage: "/audio", description: "Speech to text, microphone and spoken replies" },
  { name: "/websearch", usage: "/websearch", description: "Web search: the Brave Search API key" },
  { name: "/startup", usage: "/startup", description: "Start the assistant at boot" },
  { name: "/name", usage: "/name <name>", description: "Rename the assistant" },
  {
    name: "/pin",
    usage: "/pin <skill>",
    description: "Keep a skill's instructions on for this conversation",
  },
  { name: "/unpin", usage: "/unpin <skill>", description: "Turn a pinned skill off for this conversation" },
  { name: "/profile", usage: "/profile", description: "What the assistant knows about you: add, edit and remove" },
  { name: "/get-to-know-me", usage: "/get-to-know-me", description: "Let the assistant get to know you" },
  { name: "/help", usage: "/help", description: "Show commands and keys" },
];

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
      description: `Talk to ${a.name} directly, in a folder (alone it lets you pick one); off goes back to the assistant`,
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
