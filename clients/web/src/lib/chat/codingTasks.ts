// The coding tasks beside a conversation (core/agent_tasks/beside.py): the agent's work in each session shown as the
// conversation's messages are (ui/chat/Thread.svelte), what the panel's minimized bar says, and a session's details
// kept current from the `agent_task_step` events that bring each step as its task writes it.
import type { TaskSession, TaskSessionDetails, TaskStep, TaskTurn } from "$lib/api/types";
import { t } from "$lib/i18n.svelte";
import type { ChatItem, ToolItem, ToolStep, UserNote } from "./transcript";

export type TaskStatus = TaskSession["status"];

/** Its agent is at it. */
export function working(session: { status: TaskStatus }): boolean {
  return session.status === "running";
}

/** What the minimized panel says of them all: working while any is, else how the latest one ended; null for none. */
export function overall(sessions: readonly TaskSession[]): TaskStatus | null {
  if (sessions.some(working)) return "running";
  const latest = [...sessions].sort((a, b) => a.started_at.localeCompare(b.started_at)).at(-1);
  return latest?.status ?? null;
}

/** The session the panel shows: the one picked while it's there, else the newest. */
export function shownSession(sessions: readonly TaskSession[], picked: string | undefined): TaskSession | null {
  return sessions.find((s) => s.id === picked) ?? sessions.at(-1) ?? null;
}

/** The details with a step an event brought for `taskId`, at `index` among its steps: as they are when they have it
 * already; null when they don't have that task yet, or miss steps before it, to load them again. */
export function withStep(details: TaskSessionDetails, taskId: string, index: number, step: TaskStep): TaskSessionDetails | null {
  const turn = details.turns.find((t) => t.id === taskId);
  const steps = turn?.steps ?? [];
  if (!turn || index > steps.length) return null;
  if (index < steps.length) return details;
  const turns = details.turns.map((t) => (t === turn ? { ...t, steps: [...steps, step] } : t));
  return { ...details, turns };
}

/** The session's work as a conversation: what the agent was asked (the assistant's task, collapsed, or the user's
 * message), its thinking, what it says, its tool calls with their results and its notes, the messages the user sent it
 * while it worked, and how each task ended; then what waits to go to it next. */
export function shownItems(details: TaskSessionDetails, agent: string): ChatItem[] {
  const shown = new Shown(agent);
  details.turns.forEach((turn) => shown.turn(turn));
  details.waiting.forEach((text) => shown.user(text, "later"));
  return shown.items;
}

class Shown {
  items: ChatItem[] = [];
  private nextId = 0;
  // The current task's calls by id, a subagent's inside the call that started it, and the user's messages by id.
  private calls = new Map<string, ToolItem | ToolStep>();
  private sent = new Map<string, Extract<ChatItem, { kind: "user" }>>();
  // The call holding the notes in a row, while they come one after another.
  private notes: ToolItem | null = null;
  // It said something since what it was last asked, so its result is that.
  private spoke = false;

  constructor(private readonly agent: string) {}

  turn(turn: TaskTurn): void {
    this.calls.clear();
    this.sent.clear();
    this.notes = null;
    this.spoke = false;
    if (turn.from_user) this.user(turn.asked);
    else this.add({ kind: "brief", id: 0, text: turn.asked, agent: this.agent });
    (turn.steps ?? []).forEach((step) => this.step(step));
    // Its worker's step for one comes later; until then it waits, after what it did.
    (turn.unread ?? []).forEach((step) => this.step(step));
    if (turn.status !== "running") this.ended(turn);
  }

  user(text: string, note?: UserNote): Extract<ChatItem, { kind: "user" }> {
    const item = { kind: "user" as const, id: this.nextId++, text, files: [], ...(note ? { note } : {}) };
    this.items.push(item);
    this.notes = null;
    return item;
  }

  private add(item: ChatItem): void {
    this.items.push({ ...item, id: this.nextId++ });
    this.notes = null;
  }

  private step(step: TaskStep): void {
    if (step.within && (step.kind === "text" || step.kind === "thinking")) return;
    if (step.kind === "text") this.text(step.text);
    else if (step.kind === "thinking") this.add({ kind: "thinking", id: 0, text: step.text });
    else if (step.kind === "tool") this.call(step);
    else if (step.kind === "result") this.result(step);
    else if (step.kind === "user") this.userStep(step);
    else if (step.kind === "taken") this.taken(step.id);
    else if (step.kind === "withdrawn") this.withdrawn(step.id);
    else if (step.text) this.note(step.text);
  }

  private text(text: string): void {
    this.spoke = true;
    const last = this.items.at(-1);
    if (last?.kind === "assistant") last.text += `\n\n${text}`;
    else this.add({ kind: "assistant", id: 0, text });
  }

  private call(step: TaskStep): void {
    const args = step.detail ? { detail: step.detail } : undefined;
    const parent = step.within ? this.calls.get(step.within) : undefined;
    if (parent && isItem(parent)) {
      const inner: ToolStep = { name: step.tool, args, state: "running" };
      parent.steps = [...(parent.steps ?? []), inner];
      if (step.id) this.calls.set(step.id, inner);
      return;
    }
    const item: ToolItem = { kind: "tool", id: this.nextId++, name: step.tool, args, state: "running" };
    this.items.push(item);
    this.notes = null;
    if (step.id) this.calls.set(step.id, item);
  }

  private result(step: TaskStep): void {
    const call = this.calls.get(step.id) ?? this.lastRunning(step.tool);
    if (!call) return;
    call.output = step.text;
    call.state = "done";
  }

  private lastRunning(tool: string): ToolItem | undefined {
    return this.items.findLast((i): i is ToolItem => i.kind === "tool" && i.name === tool && i.state === "running");
  }

  /** A message the user sent it: shown once, as it was sent, then taken unless its step still waits. */
  private userStep(step: TaskStep): void {
    const shown = step.id ? this.sent.get(step.id) : undefined;
    if (shown) {
      if (!step.waiting) delete shown.note;
      return;
    }
    const item = this.user(step.text, step.waiting ? "waiting" : undefined);
    if (step.id) this.sent.set(step.id, item);
    this.spoke = false;
  }

  private taken(id: string): void {
    const shown = this.sent.get(id);
    if (shown) delete shown.note;
  }

  private withdrawn(id: string): void {
    const shown = this.sent.get(id);
    if (shown) this.items = this.items.filter((item) => item !== shown);
  }

  /** Notes in a row go inside one call named after the agent, as when a conversation is handed to it. */
  private note(text: string): void {
    const note: ToolStep = { name: text, state: "done" };
    if (this.notes) {
      this.notes.steps = [...(this.notes.steps ?? []), note];
      return;
    }
    const item: ToolItem = { kind: "tool", id: this.nextId++, name: this.agent, state: "running", steps: [note] };
    this.items.push(item);
    this.notes = item;
  }

  /** Calls left open stop where they were; what it answered, or how it ended, closes the task. */
  private ended(turn: TaskTurn): void {
    const cut = turn.status === "done" ? "done" : "cancelled";
    for (const item of this.items) {
      if (item.kind !== "tool") continue;
      if (item.state === "running") item.state = item === this.notes ? "done" : cut;
      item.steps?.forEach((step) => step.state === "running" && (step.state = cut));
    }
    for (const shown of this.sent.values()) if (shown.note === "waiting") shown.note = "untaken";
    if (turn.status === "done" && !this.spoke && turn.result) this.add({ kind: "assistant", id: 0, text: turn.result });
    else if (turn.status === "failed") this.add({ kind: "error", id: 0, message: turn.result || t("tasks.lost") });
    else if (turn.status === "stopped") this.add({ kind: "stopped", id: 0 });
  }
}

function isItem(call: ToolItem | ToolStep): call is ToolItem {
  return "kind" in call;
}
