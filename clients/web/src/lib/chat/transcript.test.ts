import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { addUser, apply, empty, endRun, fromHistory, toolRunning } from "./transcript";

const play = (events: RunEvent[]) => events.reduce(apply, addUser(empty, "hi", []));
const kinds = (events: RunEvent[]) => play(events).items.map((item) => item.kind);

describe("transcript", () => {
  it("streams text into one message until another event arrives", () => {
    const t = play([
      { type: "TextDelta", text: "Hel" },
      { type: "TextDelta", text: "lo" },
      { type: "ToolStarted", name: "bash", args: { command: "ls" } },
      { type: "TextDelta", text: "Done" },
    ]);
    expect(t.items.map((i) => (i.kind === "assistant" ? i.text : i.kind))).toEqual(["user", "Hello", "tool", "Done"]);
  });

  it("matches tool results to calls in order", () => {
    const t = play([
      { type: "ToolStarted", name: "bash", args: {} },
      { type: "ToolStarted", name: "bash", args: {} },
      { type: "ToolFinished", name: "bash", output: "first" },
    ]);
    const tools = t.items.filter((i) => i.kind === "tool");
    expect(tools.map((i) => [i.state, i.output])).toEqual([
      ["done", "first"],
      ["running", undefined],
    ]);
  });

  it("knows while a tool call runs, so the chat shows its card and not Thinking too", () => {
    expect(toolRunning(play([{ type: "ToolStarted", name: "Claude Code", args: {} }]))).toBe(true);
    const finished = play([
      { type: "ToolStarted", name: "bash", args: {} },
      { type: "ToolFinished", name: "bash", output: "ok" },
    ]);
    expect(toolRunning(finished)).toBe(false);
  });

  it("marks running tools cancelled when the run is stopped", () => {
    const t = play([{ type: "ToolStarted", name: "bash", args: {} }, { type: "Cancelled" }]);
    expect(t.items.map((i) => (i.kind === "tool" ? i.state : i.kind))).toEqual(["user", "cancelled", "stopped"]);
  });

  it("shows a subagent's calls as steps of its delegate call", () => {
    const t = play([
      { type: "ToolStarted", name: "delegate", args: {}, id: "d1" },
      { type: "ToolStarted", name: "delegate", args: {}, id: "d2" },
      { type: "ToolStarted", name: "bash", args: { command: "ls" }, within: "d2" },
      { type: "ToolStarted", name: "bash", args: { command: "pwd" }, within: "d2" },
      { type: "ToolFinished", name: "bash", output: "a.txt", within: "d2" },
      { type: "ToolFinished", name: "delegate", output: "found" },
    ]);
    const tools = t.items.filter((i) => i.kind === "tool");
    expect(tools.map((i) => [i.state, i.steps ?? []])).toEqual([
      ["done", []],
      [
        "running",
        [
          { name: "bash", args: { command: "ls" }, output: "a.txt", state: "done" },
          { name: "bash", args: { command: "pwd" }, state: "running" },
        ],
      ],
    ]);
    const stopped = apply(t, { type: "Cancelled" }).items.find((i) => i.kind === "tool" && i.callId === "d2");
    expect(stopped?.kind === "tool" && stopped.steps?.map((s) => s.state)).toEqual(["done", "cancelled"]);
  });

  it("starts a new message after the run ends", () => {
    const t = apply(endRun(play([{ type: "TextDelta", text: "a" }])), { type: "TextDelta", text: "b" });
    expect(t.items.filter((i) => i.kind === "assistant")).toHaveLength(2);
  });

  it("shows errors, transcripts and history", () => {
    expect(
      kinds([
        { type: "Transcribed", text: "hi", language: "en" },
        { type: "Error", message: "x" },
      ]),
    ).toEqual(["user", "transcript", "error"]);
    const history = fromHistory([
      { role: "user", text: "q" },
      { role: "tool", text: "bash" },
      { role: "assistant", text: "a" },
    ]);
    expect(history.items.map((i) => i.kind)).toEqual(["user", "tool", "assistant"]);
  });
});
