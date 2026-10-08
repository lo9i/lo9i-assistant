import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import type { Decision, RunEvent, Session } from "../api/types";
import { NoticeBoard } from "../notices";
import { ChatController, type ChatClient } from "./controller";

/** A daemon whose runs play the queued events. With `keepOpen`, a run stays open after them. */
class FakeDaemon implements ChatClient {
  clientId = "me";
  saved = new Set(["t1"]);
  runs: RunEvent[][] = [];
  decisions: Record<string, Decision>[] = [];
  keepOpen = false;
  conversations = { messages: async () => [{ role: "user", text: "earlier", detail: "", output: "" }] };

  sent: string[] = [];

  homeThread = async () => "home";
  newThread = async () => "t2";
  resumeThread = async (threadId: string) => {
    if (!this.saved.has(threadId)) throw new ApiError(404, `No conversation ${threadId}.`);
  };
  cancel = async () => true;
  send = (session: Session, text: string, _f: File[], signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: ${text}`);
    return this.play(signal);
  };
  resume = (_s: Session, decisions: Record<string, Decision>, signal: AbortSignal) => {
    this.decisions.push(decisions);
    return this.play(signal);
  };
  followRun = (_id: string, signal: AbortSignal) => this.play(signal);

  private async *play(signal: AbortSignal): AsyncGenerator<RunEvent> {
    for (const event of this.runs.shift() ?? []) {
      signal.throwIfAborted();
      yield event;
    }
    if (this.keepOpen) {
      await new Promise<void>((_, reject) => signal.addEventListener("abort", () => reject(signal.reason)));
    }
  }
}

const texts = (chat: ChatController) => chat.getSnapshot().transcript.items.map((i) => ("text" in i ? i.text : i.kind));

let board: NoticeBoard;

describe("ChatController", () => {
  beforeEach(() => {
    board = new NoticeBoard();
  });

  it("reopens the conversation the tab was on, with its history", async () => {
    const chat = await ChatController.open(new FakeDaemon(), "web", "t1", new NoticeBoard());
    expect(chat.getSnapshot().threadId).toBe("t1");
    expect(texts(chat)).toEqual(["earlier"]);
  });

  it("opens home in a new tab, or when the earlier one was never saved", async () => {
    for (const earlier of [null, "never-written"]) {
      const chat = await ChatController.open(new FakeDaemon(), "web", earlier, new NoticeBoard());
      expect(chat.getSnapshot().threadId).toBe("home");
      expect(texts(chat)).toEqual(["earlier"]);
    }
  });

  it("goes back home with its history", async () => {
    const chat = await ChatController.open(new FakeDaemon(), "web", "t1", board);
    await chat.startNew();
    await chat.goHome();
    expect(chat.getSnapshot().threadId).toBe("home");
    expect(texts(chat)).toEqual(["earlier"]);
  });

  it("moves to a side conversation with the brief when the user takes the suggestion", async () => {
    const daemon = new FakeDaemon();
    const request = { kind: "side_conversation", title: "Taxes", brief: "Do them.", first_message: "Carried over from home: Taxes" };
    daemon.runs = [
      [{ type: "ApprovalRequired", interrupt_id: "i1", request }],
      [{ type: "TextDelta", text: "Moved." }, { type: "Done" }],
      [{ type: "TextDelta", text: "On it." }, { type: "Done" }],
    ];
    const chat = await ChatController.open(daemon, "web", null, board);
    const sent = chat.send("let's do my taxes", []);
    await until(() => chat.getSnapshot().approval !== null);
    chat.answer({ moved: true });
    await sent;
    expect(daemon.sent).toEqual(["home: let's do my taxes", "t2: Carried over from home: Taxes"]);
    expect(chat.getSnapshot().threadId).toBe("t2");
    expect(texts(chat)).toEqual(["Carried over from home: Taxes", "On it."]);
  });

  it("asks for approvals and resumes the run with the decisions", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [
      [
        { type: "ToolStarted", name: "bash", args: { command: "rm -rf build" } },
        { type: "ApprovalRequired", interrupt_id: "i1", request: { tool: "bash" } },
      ],
      [
        { type: "ToolFinished", name: "bash", output: "The user rejected this (no)." },
        { type: "TextDelta", text: "left it" },
        { type: "Done" },
      ],
    ];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    const sent = chat.send("clean up", []);
    await until(() => chat.getSnapshot().approval !== null);
    chat.answer({ approved: false, reason: "no" });
    await sent;
    expect(daemon.decisions).toEqual([{ i1: { approved: false, reason: "no" } }]);
    expect(texts(chat)).toEqual(["earlier", "clean up", "tool", "left it"]);
    expect(chat.getSnapshot().transcript.items[2]).toMatchObject({ state: "done", output: "The user rejected this (no)." });
    expect(chat.getSnapshot().busy).toBe(false);
  });

  it("leaves a running reply behind when starting a new conversation", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[{ type: "TextDelta", text: "working" }]];
    daemon.keepOpen = true;
    const chat = await ChatController.open(daemon, "web", "t1", board);
    const sent = chat.send("long task", []);
    await until(() => texts(chat).includes("working"));
    await chat.startNew();
    await sent;
    expect(chat.getSnapshot()).toMatchObject({ threadId: "t2", busy: false });
    expect(texts(chat)).toEqual([]);
    chat.runFinished({ run_id: "r", thread_id: "t1", channel: "web", status: "ok", reply: "all done" });
    expect(board.getSnapshot().at(-1)?.text).toBe("Previous conversation finished: all done");
  });

  it("shows a run started elsewhere, not its own", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[{ type: "TextDelta", text: "from telegram" }, { type: "Done" }]];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await chat.mirror({ run_id: "r", thread_id: "t1", channel: "telegram", client_id: "", text: "hi" });
    expect(texts(chat)).toEqual(["earlier", "hi", "from telegram"]);
    await chat.mirror({ run_id: "r2", thread_id: "t1", channel: "web", client_id: "me", text: "mine" });
    expect(texts(chat)).toHaveLength(3);
  });
});

async function until(condition: () => boolean): Promise<void> {
  for (let i = 0; i < 100 && !condition(); i++) await new Promise((resolve) => setTimeout(resolve, 0));
  expect(condition()).toBe(true);
}
