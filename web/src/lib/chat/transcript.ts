// What the chat shows: past messages, then each run's events as they arrive (like
// src/assistant/gateways/cli/tui/turn.py). Pure functions, so the rules are testable without a page.
import type { RunEvent, ShownMessage } from "../api/types";

export type ChatItem =
  | { kind: "user"; id: number; text: string; files: string[]; channel?: string }
  | { kind: "assistant"; id: number; text: string }
  | { kind: "tool"; id: number; name: string; args?: Record<string, unknown>; output?: string; state: ToolState }
  | { kind: "transcript"; id: number; text: string; language: string }
  | { kind: "error"; id: number; message: string }
  | { kind: "stopped"; id: number };

export type ToolState = "running" | "done" | "cancelled";

export type Transcript = {
  items: ChatItem[];
  nextId: number;
  // The assistant message still receiving text in the current run.
  streaming: number | null;
  // Tool results carry only the tool name, so they are matched to calls in order.
  pending: Record<string, number[]>;
};

export const empty: Transcript = { items: [], nextId: 1, streaming: null, pending: {} };

export function fromHistory(messages: ShownMessage[]): Transcript {
  return messages.reduce(addShown, empty);
}

export function addUser(t: Transcript, text: string, files: string[], channel?: string): Transcript {
  return add({ ...t, streaming: null }, { kind: "user", text, files, channel });
}

/** Adds one run event. ApprovalRequired isn't shown here; the page asks for a decision. */
export function apply(t: Transcript, event: RunEvent): Transcript {
  if (event.type === "TextDelta") return addText(t, event.text);
  const ended = { ...t, streaming: null };
  switch (event.type) {
    case "ToolStarted":
      return toolStarted(ended, event.name, event.args);
    case "ToolFinished":
      return toolFinished(ended, event.name, event.output);
    case "Transcribed":
      return add(ended, { kind: "transcript", text: event.text, language: event.language });
    case "Error":
      return add(ended, { kind: "error", message: event.message });
    case "Cancelled":
      return cancelled(ended);
    default:
      return ended;
  }
}

/** A run's events ended. Its tool calls stay pending: after approvals, the resumed run reports them. */
export function endText(t: Transcript): Transcript {
  return { ...t, streaming: null };
}

/** The turn ended, or the page stopped showing it. */
export function endRun(t: Transcript): Transcript {
  return { ...t, streaming: null, pending: {} };
}

type NewItem = ChatItem extends infer I ? (I extends ChatItem ? Omit<I, "id"> : never) : never;

function add(t: Transcript, item: NewItem): Transcript {
  return { ...t, items: [...t.items, { ...item, id: t.nextId } as ChatItem], nextId: t.nextId + 1 };
}

function addShown(t: Transcript, message: ShownMessage): Transcript {
  if (message.role === "user") return add(t, { kind: "user", text: message.text, files: [] });
  if (message.role === "tool") return add(t, { kind: "tool", name: message.text, state: "done" });
  return add(t, { kind: "assistant", text: message.text });
}

function addText(t: Transcript, text: string): Transcript {
  if (t.streaming === null) {
    const started = add(t, { kind: "assistant", text });
    return { ...started, streaming: t.nextId };
  }
  return update(t, t.streaming, (item) => (item.kind === "assistant" ? { ...item, text: item.text + text } : item));
}

function toolStarted(t: Transcript, name: string, args: Record<string, unknown>): Transcript {
  const pending = { ...t.pending, [name]: [...(t.pending[name] ?? []), t.nextId] };
  return add({ ...t, pending }, { kind: "tool", name, args, state: "running" });
}

function toolFinished(t: Transcript, name: string, output: string): Transcript {
  const [id, ...rest] = t.pending[name] ?? [];
  if (id === undefined) return t;
  const finished = update(t, id, (item) => (item.kind === "tool" ? { ...item, output, state: "done" } : item));
  return { ...finished, pending: { ...t.pending, [name]: rest } };
}

function cancelled(t: Transcript): Transcript {
  const running = new Set(Object.values(t.pending).flat());
  const items = t.items.map((item) =>
    item.kind === "tool" && running.has(item.id) ? { ...item, state: "cancelled" as const } : item,
  );
  return add({ ...t, items, pending: {} }, { kind: "stopped" });
}

function update(t: Transcript, id: number, change: (item: ChatItem) => ChatItem): Transcript {
  return { ...t, items: t.items.map((item) => (item.id === id ? change(item) : item)) };
}
