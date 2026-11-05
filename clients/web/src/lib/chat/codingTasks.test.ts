import { describe, expect, it } from "vitest";
import type { TaskSession, TaskSessionDetails, TaskStep, TaskTurn } from "$lib/api/types";
import { overall, shownItems, shownSession, withStep, working } from "./codingTasks";

function session(id: string, status: TaskSession["status"], started_at = "2026-11-05T10:00:00Z"): TaskSession {
  return {
    id,
    agent: "claude-code",
    name: "Claude Code",
    title: `Task ${id}`,
    repository: "/src/app",
    status,
    started_at,
    step: "",
    waiting: 0,
  };
}

function step(kind: string, fields: Partial<TaskStep> = {}): TaskStep {
  return { kind, text: "", tool: "", detail: "", id: "", within: "", waiting: false, ...fields };
}

function turn(id: string, steps: TaskStep[], fields: Partial<TaskTurn> = {}): TaskTurn {
  return {
    id,
    asked: "Fix the tests",
    from_user: false,
    status: "running",
    started_at: "2026-11-05T10:00:00Z",
    finished_at: "",
    result: "",
    steps,
    ...fields,
  };
}

function details(turns: TaskTurn[], waiting: string[] = []): TaskSessionDetails {
  return { session: session("s1", turns.at(-1)?.status ?? "running"), turns, waiting };
}

/** What the thread shows, one line each. */
function lines(found: TaskSessionDetails): string[] {
  return shownItems(found, "Claude Code").map((item) => {
    if (item.kind === "tool")
      return `tool ${item.name} ${item.state}${item.output ? ` → ${item.output}` : ""}${item.steps ? ` [${item.steps.map((s) => `${s.name} ${s.state}`).join(", ")}]` : ""}`;
    if (item.kind === "user") return `user ${item.text}${item.note ? ` (${item.note})` : ""}`;
    if (item.kind === "error") return `error ${item.message}`;
    if (item.kind === "stopped") return "stopped";
    if (item.kind === "model" || item.kind === "held") return item.kind;
    return `${item.kind} ${item.text}`;
  });
}

describe("coding tasks beside a conversation", () => {
  it("say how they're doing all together: working while any is, else how the latest ended", () => {
    expect(overall([])).toBeNull();
    expect(overall([session("a", "done"), session("b", "running", "2026-11-05T09:00:00Z")])).toBe("running");
    expect(overall([session("a", "failed", "2026-11-05T11:00:00Z"), session("b", "done")])).toBe("failed");
    expect([session("a", "running"), session("b", "stopped")].map(working)).toEqual([true, false]);
  });

  it("show the session picked while it's there, else the newest", () => {
    const sessions = [session("a", "done"), session("b", "running")];
    expect(shownSession(sessions, "a")?.id).toBe("a");
    expect(shownSession(sessions, "gone")?.id).toBe("b");
    expect(shownSession([], undefined)).toBeNull();
  });

  it("show the agent's work as a conversation: the task, its thinking, words and calls with their results", () => {
    const steps = [
      step("thinking", { text: "The test expects a list." }),
      step("text", { text: "Running the tests." }),
      step("tool", { tool: "Bash", detail: "pytest -q", id: "t1" }),
      step("result", { tool: "Bash", text: "1 failed", id: "t1" }),
      step("text", { text: "Fixed it." }),
      step("text", { text: "All green." }),
    ];
    expect(lines(details([turn("1", steps, { status: "done", result: "All green." })]))).toEqual([
      "brief Fix the tests",
      "thinking The test expects a list.",
      "assistant Running the tests.",
      "tool Bash done → 1 failed",
      "assistant Fixed it.\n\nAll green.", // its result, said already, isn't shown again
    ]);
  });

  it("show a subagent's calls inside the call that started it, and notes in a row inside one call", () => {
    const steps = [
      step("note", { text: "Downloading the CLI" }),
      step("note", { text: "Starting" }),
      step("tool", { tool: "Task", detail: "find the bug", id: "t1" }),
      step("text", { text: "Looking for parse.", within: "t1" }),
      step("tool", { tool: "Grep", id: "s1", within: "t1" }),
      step("result", { tool: "Grep", text: "parse.py:3", id: "s1", within: "t1" }),
    ];
    expect(lines(details([turn("1", steps)]))).toEqual([
      "brief Fix the tests",
      "tool Claude Code running [Downloading the CLI done, Starting done]",
      "tool Task running [Grep done]",
    ]);
  });

  it("show the user's messages to it waiting until it takes them, and those it ended without as gone on next", () => {
    const steps = [
      step("user", { text: "use the fixtures", id: "m1", waiting: true }),
      step("user", { text: "and the docs", id: "m2", waiting: true }),
      step("user", { text: "never mind", id: "m3", waiting: true }),
      step("taken", { id: "m1" }),
      step("withdrawn", { id: "m3" }),
    ];
    expect(lines(details([turn("1", steps)]))).toEqual(["brief Fix the tests", "user use the fixtures", "user and the docs (waiting)"]);
    const ended = turn("1", steps, { status: "done", result: "Done." });
    const next = turn("2", [], { asked: "and the docs", from_user: true });
    expect(lines(details([ended, next], ["now the changelog"]))).toEqual([
      "brief Fix the tests",
      "user use the fixtures",
      "user and the docs (untaken)",
      "assistant Done.",
      "user and the docs",
      "user now the changelog (later)",
    ]);
  });

  it("show a message its worker hasn't passed on as waiting, once, taken when its step says so", () => {
    const unread = step("user", { text: "use the fixtures", id: "m1", waiting: true });
    const found = details([{ ...turn("1", [step("text", { text: "Working." })]), unread: [unread] }]);
    expect(lines(found)).toEqual(["brief Fix the tests", "assistant Working.", "user use the fixtures (waiting)"]);
    const passedOn = withStep(found, "1", 1, step("user", { text: "use the fixtures", id: "m1" }));
    expect(passedOn && lines(passedOn)).toEqual(["brief Fix the tests", "assistant Working.", "user use the fixtures"]);
  });

  it("put a step an event brought at its place: once, and loaded again when steps before it are missing", () => {
    const found = details([turn("1", [step("text", { text: "Working." })])]);
    const next = step("tool", { tool: "Bash", id: "t1" });
    expect(withStep(found, "1", 0, next)).toBe(found); // had it already
    expect(withStep(found, "1", 1, next)?.turns[0].steps).toHaveLength(2);
    expect(withStep(found, "1", 2, next)).toBeNull();
    expect(withStep(found, "2", 0, next)).toBeNull(); // a task it doesn't have yet
  });

  it("close how a task ended: calls left open stop, a failure says why, a stop says so", () => {
    const open = [step("tool", { tool: "Bash", detail: "make", id: "t1" })];
    expect(lines(details([turn("1", open, { status: "failed", result: "it broke" })]))).toEqual([
      "brief Fix the tests",
      "tool Bash cancelled",
      "error it broke",
    ]);
    expect(lines(details([turn("1", open, { status: "stopped" })])).slice(1)).toEqual(["tool Bash cancelled", "stopped"]);
    expect(lines(details([turn("1", [], { status: "failed" })]))[1]).toMatch(/^error Its worker ended without a result/);
  });
});
