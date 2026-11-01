import { describe, expect, it } from "vitest";
import type { BackgroundStep, BackgroundSubagent } from "$lib/api/types";
import { asked, counts, taskTitle, withStep, working } from "./subagents";

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
    result: "",
    waiting,
  };
}

function step(index: number, done = false): BackgroundStep {
  return { index, call_id: `c${index}`, name: "bash", args: { command: "ls" }, output: done ? "a" : "", done };
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
});
