import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import { addCarried, addNotice, addUser, apply, empty, endRun, fromHistory, inlineArg, toolRunning } from "./transcript";

const play = (events: RunEvent[]) => events.reduce(apply, addUser(empty, "hi", []));
const kinds = (events: RunEvent[]) => play(events).items.map((item) => item.kind);

describe("transcript", () => {
  it("shows a quick exchange carried from the inbox before the message that followed it up", () => {
    const t = fromHistory([
      { role: "carried", text: "**You:** how far?", detail: "", output: "", dispatch_id: "" },
      { role: "user", text: "plan the drive", detail: "", output: "", dispatch_id: "" },
    ]);
    expect(t.items.map((i) => i.kind)).toEqual(["carried", "user"]);
    const followed = fromHistory([{ role: "notice", text: "⚠️ convert: it failed", detail: "", output: "", dispatch_id: "" }]);
    expect(followed.items[0]).toMatchObject({ kind: "notice", text: "⚠️ convert: it failed" });
    expect(addCarried(empty, "**You:** how far?").items[0]).toMatchObject({ kind: "carried", text: "**You:** how far?" });
    // A follow-up run started elsewhere shows what it follows up on as it starts, as history does.
    expect(addNotice(empty, "⚠️ convert: it failed").items[0]).toMatchObject({ kind: "notice", text: "⚠️ convert: it failed" });
  });

  it("streams text into one message until another event arrives", () => {
    const t = play([
      { type: "TextDelta", text: "Hel" },
      { type: "TextDelta", text: "lo" },
      { type: "ToolStarted", name: "bash", args: { command: "ls" } },
      { type: "TextDelta", text: "Done" },
    ]);
    expect(t.items.map((i) => (i.kind === "assistant" ? i.text : i.kind))).toEqual(["user", "Hello", "tool", "Done"]);
  });

  it("shows a message sent to a working agent among its steps, and its words after it as a new message", () => {
    const t = play([
      { type: "TextDelta", text: "Running the tests" },
      { type: "ToolStarted", name: "Bash", args: { detail: "pytest" } },
      { type: "UserSaid", text: "skip the slow ones" },
      { type: "TextDelta", text: "Skipping them" },
    ]);
    expect(t.items.map((i) => (i.kind === "assistant" || i.kind === "user" ? i.text : i.kind))).toEqual([
      "hi",
      "Running the tests",
      "tool",
      "skip the slow ones",
      "Skipping them",
    ]);
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

  it("shows a handed-off agent's thinking apart from its text", () => {
    const t = play([
      { type: "Thinking", text: "The test expects a list." },
      { type: "TextDelta", text: "Running the tests." },
      { type: "Thinking", text: "It failed." },
      { type: "TextDelta", text: "Fixed it." },
    ]);
    expect(t.items.map((i) => (i.kind === "thinking" || i.kind === "assistant" ? `${i.kind}: ${i.text}` : i.kind))).toEqual([
      "user",
      "thinking: The test expects a list.",
      "assistant: Running the tests.",
      "thinking: It failed.",
      "assistant: Fixed it.",
    ]);
  });

  it("joins thinking that streams into one item", () => {
    const t = play([
      { type: "Thinking", text: "The test " },
      { type: "Thinking", text: "expects a list." },
      { type: "TextDelta", text: "Fixing it." },
      { type: "Thinking", text: "Done?" },
    ]);
    expect(t.items.filter((i) => i.kind === "thinking").map((i) => (i.kind === "thinking" ? i.text : ""))).toEqual([
      "The test expects a list.",
      "Done?",
    ]);
  });

  it("shows a call's one text argument next to its name", () => {
    expect(inlineArg({ detail: "pytest -q" })).toBe("pytest -q");
    expect(inlineArg({ command: "ls", timeout: 5 })).toBeUndefined();
    expect(inlineArg({ todos: [] })).toBeUndefined();
    expect(inlineArg({})).toBeUndefined();
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
      { role: "user", text: "q", detail: "", output: "", dispatch_id: "" },
      { role: "tool", text: "bash", detail: "", output: "", dispatch_id: "" },
      { role: "assistant", text: "a", detail: "", output: "", dispatch_id: "" },
    ]);
    expect(history.items.map((i) => i.kind)).toEqual(["user", "tool", "assistant"]);
  });

  it("shows a delegate call's task, the subagent's steps and its answer again in history", () => {
    const steps = [{ name: "bash", args: { command: "grep -r token logs" }, output: "token=42" }];
    const history = fromHistory([
      { role: "tool", text: "delegate", detail: "Find the token", output: "It's 42.", dispatch_id: "", steps },
      { role: "tool", text: "bash", detail: "", output: "", dispatch_id: "", steps: [] },
    ]);
    expect(history.items[0]).toMatchObject({
      kind: "tool",
      name: "delegate",
      args: { detail: "Find the token" },
      output: "It's 42.",
      state: "done",
      steps: [{ name: "bash", args: { command: "grep -r token logs" }, output: "token=42", state: "done" }],
    });
    expect(history.items[1]).not.toHaveProperty("steps");
  });

  it("shows a handed-off agent's thinking and tool calls again in history", () => {
    const history = fromHistory([
      { role: "thinking", text: "The test expects a list.", detail: "", output: "", dispatch_id: "" },
      { role: "tool", text: "Bash", detail: "pytest -q", output: "1 failed", dispatch_id: "" },
    ]);
    expect(history.items).toEqual([
      { kind: "thinking", id: 1, text: "The test expects a list." },
      { kind: "tool", id: 2, name: "Bash", args: { detail: "pytest -q" }, output: "1 failed", state: "done" },
    ]);
  });
});
