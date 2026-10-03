// The web UI's slash commands, like src/assistant/gateways/cli/commands.py. The terminal's /mouse
// and /quit have no meaning in a browser; /settings opens the settings page.

export type Command = { name: string; usage: string; description: string };

export const COMMANDS: Command[] = [
  { name: "/new", usage: "/new", description: "Start a new conversation" },
  { name: "/conversations", usage: "/conversations", description: "Earlier conversations, to resume one" },
  { name: "/attach", usage: "/attach", description: "Attach files to the next message" },
  { name: "/sessions", usage: "/sessions", description: "Clients connected to the daemon" },
  { name: "/jobs", usage: "/jobs", description: "Scheduled jobs" },
  { name: "/settings", usage: "/settings", description: "Name, appearance, start at boot, integrations, audio and MCP servers" },
  { name: "/mcp", usage: "/mcp", description: "MCP servers and their tools" },
  { name: "/plugins", usage: "/plugins", description: "Install, update and remove plugins from the extras" },
  { name: "/skills", usage: "/skills", description: "Browse, install and delete skills" },
  { name: "/usage", usage: "/usage", description: "Tool and skill usage" },
  { name: "/telegram", usage: "/telegram", description: "Connect Telegram" },
  { name: "/slack", usage: "/slack", description: "Connect Slack" },
  { name: "/audio", usage: "/audio", description: "Speech to text, microphone and spoken replies" },
  { name: "/email", usage: "/email", description: "Connect email for sending" },
  { name: "/websearch", usage: "/websearch", description: "Web search: the Brave Search API key" },
  { name: "/startup", usage: "/startup", description: "Start the assistant at boot" },
  { name: "/name", usage: "/name <name>", description: "Rename the assistant" },
  { name: "/profile", usage: "/profile", description: "What the assistant knows about you: add, edit and remove" },
  { name: "/get-to-know-me", usage: "/get-to-know-me", description: "Let the assistant get to know you" },
  { name: "/help", usage: "/help", description: "Show commands and keys" },
];

export function takesArgument(command: Command): boolean {
  return command.usage !== command.name;
}

/** Commands to offer while the command name is being typed: text starting with / and no space yet. */
export function offered(text: string): Command[] {
  if (!text.startsWith("/") || /\s/.test(text)) return [];
  return COMMANDS.filter((c) => c.name.startsWith(text));
}

/** A typed command line, split into the command and its argument; null for a message. */
export function parse(text: string): { name: string; arg: string } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const space = trimmed.search(/\s/);
  if (space < 0) return { name: trimmed, arg: "" };
  return { name: trimmed.slice(0, space), arg: trimmed.slice(space).trim() };
}

export function known(name: string): boolean {
  return COMMANDS.some((c) => c.name === name);
}

/** What /get-to-know-me and the Settings button send: the get-to-know-you skill starts from it. */
export const GET_TO_KNOW_ME = "Get to know me.";
