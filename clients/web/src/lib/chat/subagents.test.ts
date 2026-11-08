import { describe, expect, it } from "vitest";
import type { BackgroundStep, BackgroundSubagent } from "$lib/api/types";
import { asked, conversationTitle, counts, doing, taskTitle, withStep, working } from "./subagents";

function subagent(status: BackgroundSubagent["status"], waiting: BackgroundSubagent["waiting"] = []): BackgroundSubagent {
  return {
    id: status,
    user_id: "owner",
    thread_id: "t1",
    channel: "web",
    task: "Find flights\nCheapest first",
    agent: "",
    plugins: [],
    started_at: "2026-11-01T10:00:00Z",
    status,
    ended_at: "",
    step: "",
    steps: 0,
    model_calls: 0,
    context_tokens: 0,
    context_limit: 0,
    result: "",
    waiting,
  };
}

function step(index: number, done = false): BackgroundStep {
  return { index, call_id: `c${index}`, name: "bash", args: { command: "ls" }, output: done ? "a" : "", done, at: "" };
}

describe("background subagents", () => {
  it("count those at it and those waiting for the user", () => {
    const list = [subagent("running"), subagent("waiting"), subagent("done"), subagent("failed"), subagent("stopped")];
    expect(list.map(working)).toEqual([true, true, false, false, false]);
    expect(counts(list)).toEqual({ working: 2, waiting: 1 });
  });

  it("are named by their task's first line", () => {
    expect(taskTitle("  Find flights\nCheapest first")).toBe("Find flights");
  });

  it("show what they wait for as a run's approval", () => {
    const waiting = subagent("waiting", [{ interrupt_id: "i1", request: { tool: "bash", command: "rm -rf build" } }]);
    expect(asked(waiting)).toEqual([{ type: "ApprovalRequired", interrupt_id: "i1", request: { tool: "bash", command: "rm -rf build" } }]);
  });

  it("keep their steps in order as events start and finish them", () => {
    const started = withStep([step(0, true)], step(1));
    expect(started.map((s) => [s.index, s.done])).toEqual([
      [0, true],
      [1, false],
    ]);
    expect(withStep(started, step(1, true)).map((s) => [s.index, s.done])).toEqual([
      [0, true],
      [1, true],
    ]);
  });

  it("say what they're doing, or how they ended", () => {
    expect(doing({ ...subagent("running"), step: "bash ls" })).toBe("bash ls");
    expect(doing(subagent("running"))).toBe("Thinking…");
    expect(doing(subagent("waiting"))).toBe("Waiting for your answer");
    expect(doing({ ...subagent("failed"), result: "RuntimeError: down" })).toBe("RuntimeError: down");
  });

  it("name the conversation they work for by its title", () => {
    const listed = [
      { thread_id: "t1", title: "Flights to Rome" },
      { thread_id: "t2", title: "" },
    ];
    expect(conversationTitle("t1", listed)).toBe("Flights to Rome");
    expect(conversationTitle("t2", listed)).toBe("Untitled");
    expect(conversationTitle("gone", listed)).toBe("Untitled");
  });
});
