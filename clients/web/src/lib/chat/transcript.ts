// What the chat shows: past messages, then each run's events as they arrive (like
// src/assistant/gateways/cli/tui/turn.py). Pure functions, so the rules are testable without a page.
import type { RunEvent, ShownCall, ShownMessage } from "../api/types";

export type ChatItem =
  | { kind: "user"; id: number; text: string; files: string[]; channel?: string }
  // `dispatchId`: the inbox's record of a message it sent on, which can be moved.
  | { kind: "assistant"; id: number; text: string; dispatchId?: string }
  | { kind: "thinking"; id: number; text: string }
  // A quick exchange the inbox carried to this conversation, as Markdown, before the message that followed it up.
  | { kind: "carried"; id: number; text: string }
  // Background work that ended, which the assistant followed up on without a message from the user.
  | { kind: "notice"; id: number; text: string }
  | ToolItem
  | { kind: "transcript"; id: number; text: string; language: string }
  | { kind: "error"; id: number; message: string }
  | { kind: "stopped"; id: number };

export type ToolState = "running" | "done" | "cancelled";

/** A tool call. A delegate call's subagent reports its own calls as `steps`. One from history that's `partial`
 * shows its arguments on one line and the start of its output: the whole call loads by `callId` when opened. */
export type ToolItem = ToolStep & { kind: "tool"; id: number; callId?: string; partial?: boolean; steps?: ToolStep[] };

export type ToolStep = { name: string; args?: Record<string, unknown>; output?: string; state: ToolState };

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

/** The latest answer: assistant text after the last message or tool call, for reading aloud. */
export function finalReply(t: Transcript): string {
  const last = t.items.findLastIndex((item) => item.kind !== "assistant");
  return t.items
    .slice(last + 1)
    .map((item) => (item.kind === "assistant" ? item.text : ""))
    .join("")
    .trim();
}

/** What a follow-up the assistant runs on its own follows up on (background work that ended), where the user's
 * message would be, as history shows it. */
export function addNotice(t: Transcript, text: string): Transcript {
  return add({ ...t, streaming: null }, { kind: "notice", text });
}

/** A quick exchange the inbox carried here, shown before the message that followed it up. */
export function addCarried(t: Transcript, text: string): Transcript {
  return add({ ...t, streaming: null }, { kind: "carried", text });
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
      if (event.within) return stepStarted(ended, event.within, { name: event.name, args: event.args, state: "running" });
      return toolStarted(ended, event.name, event.args, event.id);
    case "ToolFinished":
      if (event.within) return stepFinished(ended, event.within, event.name, event.output);
      return toolFinished(ended, event.name, event.output);
    case "Thinking":
      return addThinking(ended, event.text);
    case "UserSaid":
      return add(ended, { kind: "user", text: event.text, files: [] });
    case "Transcribed":
      return add(ended, { kind: "transcript", text: event.text, language: event.language });
    case "Dispatched":
      // As the inbox records it (core/conversation/dispatch_nodes.py), so history reads the same.
      return add(ended, { kind: "assistant", text: event.line, dispatchId: event.id });
    case "Error":
      return add(ended, { kind: "error", message: event.message });
    case "Cancelled":
      return cancelled(ended);
    default:
      return ended;
  }
}

/** A call's one argument when it's text or a number (a command, a file), shown next to its name. */
export function inlineArg(args?: Record<string, unknown>): string | undefined {
  const values = Object.values(args ?? {});
  const [value] = values;
  return values.length === 1 && (typeof value === "string" || typeof value === "number") ? String(value) : undefined;
}

/** A run's events ended. Its tool calls stay pending: after approvals, the resumed run reports them. */
/** A tool call is running: its card shows that the reply is in progress. */
export function toolRunning(t: Transcript): boolean {
  return t.items.some((item) => item.kind === "tool" && item.state === "running");
}

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
  if (message.role === "thinking") return add(t, { kind: "thinking", text: message.text });
  if (message.role === "carried") return add(t, { kind: "carried", text: message.text });
  if (message.role === "notice") return add(t, { kind: "notice", text: message.text });
  if (message.role === "tool") return add(t, shownTool(message));
  return add(t, { kind: "assistant", text: message.text, dispatchId: message.dispatch_id || undefined });
}

/** A handed-off agent's tool call comes with what it was about and its output, a delegate call with its task,
 * the subagent's steps and its answer, as they were shown live. Any other call comes with its arguments on one
 * line and the start of its output, `partial` when the whole call is worth loading (`withWhole`). */
function shownTool(message: ShownMessage): Omit<ToolItem, "id"> {
  const args = message.detail ? { detail: message.detail } : undefined;
  const steps = message.steps?.map((s): ToolStep => ({ name: s.name, args: s.args, output: s.output, state: "done" }));
  const item = { kind: "tool" as const, name: message.text, args, output: message.output || undefined, state: "done" as const };
  const call = { ...item, ...(message.call_id ? { callId: message.call_id } : {}), ...(message.partial ? { partial: true } : {}) };
  return steps?.length ? { ...call, steps } : call;
}

/** A call from history with all its arguments and its whole output, loaded when it was opened. */
export function withWhole(item: ToolItem, call: ShownCall): ToolItem {
  return { ...item, args: call.args, output: call.output || undefined, partial: false };
}

/** Thinking streams: an event right after another continues it. */
function addThinking(t: Transcript, text: string): Transcript {
  const last = t.items.at(-1);
  if (last?.kind !== "thinking") return add(t, { kind: "thinking", text });
  return update(t, last.id, (item) => (item.kind === "thinking" ? { ...item, text: item.text + text } : item));
}

function addText(t: Transcript, text: string): Transcript {
  if (t.streaming === null) {
    const started = add(t, { kind: "assistant", text });
    return { ...started, streaming: t.nextId };
  }
  return update(t, t.streaming, (item) => (item.kind === "assistant" ? { ...item, text: item.text + text } : item));
}

function toolStarted(t: Transcript, name: string, args: Record<string, unknown>, callId?: string): Transcript {
  const pending = { ...t.pending, [name]: [...(t.pending[name] ?? []), t.nextId] };
  return add({ ...t, pending }, { kind: "tool", name, args, callId, state: "running" });
}

function stepStarted(t: Transcript, within: string, step: ToolStep): Transcript {
  return updateCall(t, within, (steps) => [...steps, step]);
}

/** Results carry only the tool name, so they finish the call's first running step of that name. */
function stepFinished(t: Transcript, within: string, name: string, output: string): Transcript {
  return updateCall(t, within, (steps) => {
    const index = steps.findIndex((s) => s.name === name && s.state === "running");
    return steps.map((s, i) => (i === index ? { ...s, output, state: "done" } : s));
  });
}

function updateCall(t: Transcript, callId: string, change: (steps: ToolStep[]) => ToolStep[]): Transcript {
  const items = t.items.map((item) =>
    item.kind === "tool" && item.callId === callId ? { ...item, steps: change(item.steps ?? []) } : item,
  );
  return { ...t, items };
}

function toolFinished(t: Transcript, name: string, output: string): Transcript {
  const [id, ...rest] = t.pending[name] ?? [];
  if (id === undefined) return t;
  const finished = update(t, id, (item) => (item.kind === "tool" ? { ...item, output, state: "done" } : item));
  return { ...finished, pending: { ...t.pending, [name]: rest } };
}

function cancelled(t: Transcript): Transcript {
  const running = new Set(Object.values(t.pending).flat());
  const items = t.items.map((item) => (item.kind === "tool" && running.has(item.id) ? cancelCall(item) : item));
  return add({ ...t, items, pending: {} }, { kind: "stopped" });
}

function cancelCall(item: ToolItem): ToolItem {
  const steps = item.steps?.map((s) => (s.state === "running" ? { ...s, state: "cancelled" as const } : s));
  return { ...item, steps, state: "cancelled" };
}

function update(t: Transcript, id: number, change: (item: ChatItem) => ChatItem): Transcript {
  return { ...t, items: t.items.map((item) => (item.id === id ? change(item) : item)) };
}
