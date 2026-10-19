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
  conversations = {
    messages: async () => [{ role: "user", text: "earlier", detail: "", output: "", dispatch_id: "" }],
  };

  sent: string[] = [];

  inboxThread = async () => "inbox";
  newThread = async () => "t2";
  resumeThread = async (threadId: string) => {
    if (!this.saved.has(threadId)) throw new ApiError(404, `No conversation ${threadId}.`);
  };
  left = 0;
  leaveThread = async () => {
    this.left += 1;
  };
  cancel = async () => true;
  send = (session: Session, text: string, _f: File[], signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: ${text}`);
    return this.play(signal);
  };
  sendDispatched = (session: Session, id: string, text: string, signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: ${text} (${id})`);
    return this.play(signal);
  };
  moveDispatched = (session: Session, id: string, signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: move ${id}`);
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

  it("opens the inbox in a new tab, or when the earlier one was never saved", async () => {
    for (const earlier of [null, "never-written"]) {
      const chat = await ChatController.open(new FakeDaemon(), "web", earlier, new NoticeBoard());
      expect(chat.getSnapshot().threadId).toBe("inbox");
      expect(texts(chat)).toEqual(["earlier"]);
    }
  });

  it("goes back to the inbox with its history", async () => {
    const chat = await ChatController.open(new FakeDaemon(), "web", "t1", board);
    await chat.startNew();
    await chat.goInbox();
    expect(chat.getSnapshot().threadId).toBe("inbox");
    expect(texts(chat)).toEqual(["earlier"]);
  });

  it("knows the inbox, so the page can tell a conversation from it", async () => {
    const daemon = new FakeDaemon();
    const chat = await ChatController.open(daemon, "web", "t1", board);
    expect(chat.getSnapshot()).toMatchObject({ threadId: "t1", inboxId: "inbox" });
    await chat.goInbox();
    expect(chat.getSnapshot()).toMatchObject({ threadId: "inbox", inboxId: "inbox" });
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

  it("goes where the inbox sent a message on and sends it there", async () => {
    const daemon = new FakeDaemon();
    const dispatched = {
      type: "Dispatched",
      id: "d1",
      thread_id: "",
      title: "New conversation",
      text: "plan my week",
      line: "→ Started a new conversation.",
    } as const;
    daemon.runs = [
      [dispatched, { type: "Done" }],
      [{ type: "TextDelta", text: "A plan." }, { type: "Done" }],
    ];
    const chat = await ChatController.open(daemon, "web", null, board);
    await chat.send("plan my week", []);
    expect(daemon.sent).toEqual(["inbox: plan my week", "t2: plan my week (d1)"]);
    expect(chat.getSnapshot().threadId).toBe("t2");
    expect(texts(chat)).toEqual(["plan my week", "A plan."]);
  });

  it("hands where the inbox sent a message on to whoever shows it, when someone does", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [
      [
        { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Continued in “Trip”." },
        { type: "Done" },
      ],
    ];
    const chat = await ChatController.open(daemon, "web", null, board);
    const handed: string[] = [];
    chat.onDispatched = async (d) => void handed.push(d.thread_id);
    await chat.send("flights?", []);
    expect(handed).toEqual(["t1"]);
    expect(chat.getSnapshot().threadId).toBe("inbox");
    expect(texts(chat)).toEqual(["earlier", "flights?", "→ Continued in “Trip”."]);
  });

  it("moves a message the inbox sent on and sends it where it goes now", async () => {
    const daemon = new FakeDaemon();
    const moved = {
      type: "Dispatched",
      id: "d1",
      thread_id: "t1",
      title: "Trip",
      text: "flights?",
      line: "→ Moved “flights?” to “Trip”.",
    } as const;
    daemon.runs = [[moved, { type: "Done" }], [{ type: "Done" }]];
    const chat = await ChatController.open(daemon, "web", null, board);
    await chat.move("d1");
    expect(daemon.sent).toEqual(["inbox: move d1", "t1: flights? (d1)"]);
    expect(chat.getSnapshot().threadId).toBe("t1");
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
