import { describe, expect, it } from "vitest";
import type { RunEvent } from "../api/types";
import {
  addBrief,
  addCarried,
  addNotice,
  addUser,
  apply,
  empty,
  endRun,
  fromHistory,
  inlineArg,
  pinnable,
  showedHeld,
  toolRunning,
  withWhole,
} from "./transcript";

const play = (events: RunEvent[]) => events.reduce(apply, addUser(empty, "hi", []));
const kinds = (events: RunEvent[]) => play(events).items.map((item) => item.kind);

describe("transcript", () => {
  it("shows a quick exchange carried from the inbox before the message that followed it up", () => {
    const t = fromHistory([
      {
        role: "carried",
        text: "**You:** how far?",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "user",
        text: "plan the drive",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(t.items.map((i) => i.kind)).toEqual(["carried", "user"]);
    const followed = fromHistory([
      {
        role: "notice",
        text: "⚠️ convert: it failed",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(followed.items[0]).toMatchObject({ kind: "notice", text: "⚠️ convert: it failed" });
    expect(addCarried(empty, "**You:** how far?").items[0]).toMatchObject({ kind: "carried", text: "**You:** how far?" });
    // A follow-up run started elsewhere shows what it follows up on as it starts, as history does.
    expect(addNotice(empty, "⚠️ convert: it failed").items[0]).toMatchObject({ kind: "notice", text: "⚠️ convert: it failed" });
  });

  it("marks what waits for an update to install as it was marked when it was sent", () => {
    const t = fromHistory([
      {
        role: "user",
        text: "earlier",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "user",
        text: "still there?",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "h1",
        untaken: false,
        resent: false,
      },
    ]);
    expect(t.items.map((i) => i.kind)).toEqual(["user", "user", "held"]);
    expect(t.items[2]).toMatchObject({ kind: "held", heldId: "h1" });
    expect(showedHeld(t, "h1")).toBe(true);
  });

  it("shows a task the assistant wrote for its agent as its brief, never as the user's message, and pins only theirs", () => {
    const t = fromHistory([
      {
        role: "user",
        text: "fix the tests with claude",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "brief",
        text: "Fix the failing tests",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "Claude Code",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(t.items[1]).toEqual({ kind: "brief", id: 2, text: "Fix the failing tests", agent: "Claude Code" });
    // A run that sends one, followed from its start, shows it as history does.
    expect(addBrief(empty, "Fix the failing tests", "Claude Code").items[0]).toMatchObject({ kind: "brief", agent: "Claude Code" });
    expect(t.items.filter(pinnable).map((i) => i.text)).toEqual(["fix the tests with claude"]);
  });

  it("shows a run that failed with the error it ended with, as it showed live", () => {
    const t = fromHistory([
      {
        role: "user",
        text: "remember my goal",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "error",
        text: "OperationalError: database is locked",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(t.items[1]).toMatchObject({ kind: "error", message: "OperationalError: database is locked" });
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
      { type: "UserSaid", text: "skip the slow ones", files: ["slow.txt"] },
      { type: "TextDelta", text: "Skipping them" },
    ]);
    expect(t.items.map((i) => (i.kind === "assistant" || i.kind === "user" ? i.text : i.kind))).toEqual([
      "hi",
      "Running the tests",
      "tool",
      "skip the slow ones",
      "Skipping them",
    ]);
    expect(t.items.find((i) => i.kind === "user" && i.text === "skip the slow ones")).toMatchObject({ files: ["slow.txt"] });
  });

  it("shows a message the agent gets to later as waiting until it takes it, and as not taken once the run stops", () => {
    const t = play([
      { type: "UserSaid", text: "look at the docs", id: "m1", waiting: true },
      { type: "UserSaid", text: "skip the slow ones", id: "m2", waiting: true },
      { type: "UserTaken", id: "m1" },
    ]);
    const notes = (items: typeof t.items) => items.flatMap((i) => (i.kind === "user" ? [[i.text, i.note]] : []));
    expect(notes(t.items)).toEqual([
      ["hi", undefined],
      ["look at the docs", undefined],
      ["skip the slow ones", "waiting"],
    ]);
    expect(notes(apply(t, { type: "Cancelled" }).items).at(-1)).toEqual(["skip the slow ones", "untaken"]);
    expect(notes(apply(t, { type: "Error", message: "it broke" }).items).at(-1)).toEqual(["skip the slow ones", "untaken"]);
  });

  it("shows the messages the agent never got to, and those sent again, as history kept them", () => {
    const shown = { detail: "", output: "", dispatch_id: "", call_id: "", partial: false, agent: "", held: "" };
    const t = fromHistory([
      { role: "user", text: "skip the slow ones", ...shown, untaken: true, resent: false },
      { role: "user", text: "skip the slow ones", ...shown, untaken: false, resent: true },
    ]);
    expect(t.items.map((i) => i.kind === "user" && i.note)).toEqual(["untaken", "resent"]);
    expect(addUser(empty, "skip the slow ones", [], undefined, "resent").items[0]).toMatchObject({ note: "resent" });
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

  it("notes a message kept while an update installs, so its run later doesn't show it twice", () => {
    const t = play([{ type: "Held", id: "h1" }]);
    expect(t.items.map((i) => i.kind)).toEqual(["user", "held"]);
    expect(showedHeld(t, "h1")).toBe(true);
    expect(showedHeld(t, "h2")).toBe(false);
    expect(showedHeld(t, undefined)).toBe(false);
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
      {
        role: "user",
        text: "q",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "tool",
        text: "bash",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "assistant",
        text: "a",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(history.items.map((i) => i.kind)).toEqual(["user", "tool", "assistant"]);
  });

  it("shows a delegate call's task, the subagent's steps and its answer again in history", () => {
    const steps = [
      { name: "bash", args: { command: "grep -r token logs" }, output: "token=42", partial: false },
      { name: "bash", args: { command: "cat log" }, output: "line…", partial: true },
    ];
    const history = fromHistory([
      {
        role: "tool",
        text: "delegate",
        detail: "Find the token",
        output: "It's 42.",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
        steps,
      },
      {
        role: "tool",
        text: "bash",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
        steps: [],
      },
    ]);
    expect(history.items[0]).toMatchObject({
      kind: "tool",
      name: "delegate",
      args: { detail: "Find the token" },
      output: "It's 42.",
      state: "done",
      steps: [
        { name: "bash", args: { command: "grep -r token logs" }, output: "token=42", state: "done" },
        { name: "bash", args: { command: "cat log" }, output: "line…", state: "done", partial: true },
      ],
    });
    expect(history.items[0].kind === "tool" && history.items[0].steps?.[0]).not.toHaveProperty("partial");
    expect(history.items[1]).not.toHaveProperty("steps");
  });

  it("shows a handed-off agent's thinking and tool calls again in history", () => {
    const history = fromHistory([
      {
        role: "thinking",
        text: "The test expects a list.",
        detail: "",
        output: "",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "tool",
        text: "Bash",
        detail: "pytest -q",
        output: "1 failed",
        dispatch_id: "",
        call_id: "",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]);
    expect(history.items).toEqual([
      { kind: "thinking", id: 1, text: "The test expects a list." },
      { kind: "tool", id: 2, name: "Bash", args: { detail: "pytest -q" }, output: "1 failed", state: "done" },
    ]);
  });

  it("shows a call from history by its start, and in full once it has loaded", () => {
    const [preview, whole] = fromHistory([
      {
        role: "tool",
        text: "bash",
        detail: "seq 1 100",
        output: "1\n2…",
        dispatch_id: "",
        call_id: "c1",
        partial: true,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
      {
        role: "tool",
        text: "bash",
        detail: "ls",
        output: "a.txt",
        dispatch_id: "",
        call_id: "c2",
        partial: false,
        agent: "",
        held: "",
        untaken: false,
        resent: false,
      },
    ]).items;
    expect(preview).toEqual({
      kind: "tool",
      id: 1,
      name: "bash",
      args: { detail: "seq 1 100" },
      output: "1\n2…",
      state: "done",
      callId: "c1",
      partial: true,
    });
    expect(whole).toEqual({ kind: "tool", id: 2, name: "bash", args: { detail: "ls" }, output: "a.txt", state: "done", callId: "c2" });
    if (preview.kind !== "tool") throw new Error("not a tool call");
    expect(inlineArg(preview.args)).toBe("seq 1 100");
    const loaded = withWhole(preview, { name: "bash", args: { command: "seq 1 100", timeout: 5 }, output: "1\n2\n3" });
    expect(loaded).toMatchObject({ args: { command: "seq 1 100", timeout: 5 }, output: "1\n2\n3", partial: false, callId: "c1" });
    expect(inlineArg(loaded.args)).toBeUndefined();
  });
});
