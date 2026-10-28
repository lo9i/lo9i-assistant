import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import type { ApprovalRequired, Decision, Dispatched, RunEvent, RunInProgress, Session } from "../api/types";
import { NoticeBoard } from "../notices";
import { ChatController, type ChatClient } from "./controller";
import { ChatTab } from "./tab";
import { finalReply } from "./transcript";

/** A daemon whose runs play the queued events, those followed and those in progress in a conversation alike. With
 * `keepOpen`, a run stays open after them, and with `holding` until it resolves; with `slowHistory`, a conversation's
 * history loads once it resolves. */
class FakeDaemon implements ChatClient {
  clientId = "me";
  saved = new Set(["t1"]);
  runs: RunEvent[][] = [];
  decisions: Record<string, Decision>[] = [];
  keepOpen = false;
  holding: Promise<void> | null = null;
  // What a conversation's run stopped for and waits on, until it's resumed.
  waiting = new Map<string, ApprovalRequired[]>();
  // The runs in progress in each conversation, oldest first.
  inProgress = new Map<string, RunInProgress[]>();
  slowHistory: Promise<void> | null = null;
  loading: string[] = [];
  followed: string[] = [];
  // Where `route` sends a first message; "" for where it was written.
  routes = new Map<string, string>();
  routed: string[] = [];
  conversations = {
    live: async (threadId: string) => {
      this.loading.push(threadId);
      await this.slowHistory;
      const messages = [{ role: "user", text: "earlier", detail: "", output: "", dispatch_id: "", call_id: "", partial: false, agent: "" }];
      return { messages, runs: this.inProgress.get(threadId) ?? [] };
    },
    approvals: async (threadId: string) => this.waiting.get(threadId) ?? [],
    route: async (text: string) => {
      this.routed.push(text);
      return this.routes.get(text) ?? "";
    },
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
  sendDispatched = (session: Session, dispatched: Dispatched, signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: ${dispatched.text} (${dispatched.id})`);
    return this.play(signal);
  };
  moveDispatched = (session: Session, id: string, signal: AbortSignal) => {
    this.sent.push(`${session.thread_id}: move ${id}`);
    return this.play(signal);
  };
  resume = (session: Session, decisions: Record<string, Decision>, signal: AbortSignal) => {
    this.decisions.push(decisions);
    this.waiting.delete(session.thread_id);
    return this.play(signal);
  };
  followRunBatches = (id: string, signal: AbortSignal) => {
    this.followed.push(id);
    return this.playAtOnce(signal);
  };

  /** As the daemon replays a run's past events to a page following it from its start: in one read. */
  private async *playAtOnce(signal: AbortSignal): AsyncGenerator<RunEvent[]> {
    const events = this.runs.shift() ?? [];
    signal.throwIfAborted();
    if (events.length) yield events;
    await this.heldOpen(signal);
  }

  private async heldOpen(signal: AbortSignal): Promise<void> {
    if (this.keepOpen) {
      await new Promise<void>((_, reject) => signal.addEventListener("abort", () => reject(signal.reason)));
    }
    await this.holding;
  }

  private async *play(signal: AbortSignal): AsyncGenerator<RunEvent> {
    for (const event of this.runs.shift() ?? []) {
      signal.throwIfAborted();
      yield event;
    }
    await this.heldOpen(signal);
  }
}

const inProgress = (run_id: string, text: string, client_id = "me"): RunInProgress => ({
  run_id,
  thread_id: "t1",
  channel: client_id ? "web" : "telegram",
  client_id,
  text,
  notice: "",
  brief: "",
});

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

  it("opens a new conversation in Chat instead of the inbox: none before, one gone, or the inbox itself", async () => {
    const daemon = new FakeDaemon();
    daemon.saved.add("inbox");
    for (const earlier of [null, "never-written", "inbox"]) {
      const chat = await ChatController.openInChat(daemon, "web", earlier, new NoticeBoard());
      expect(chat.getSnapshot()).toMatchObject({ threadId: "t2", inboxId: "inbox" });
      expect(texts(chat)).toEqual([]);
    }
    const chat = await ChatController.openInChat(daemon, "web", "t1", new NoticeBoard());
    expect(chat.getSnapshot().threadId).toBe("t1");
  });

  it("sends the first message of a conversation opened for none where it goes, and later ones here", async () => {
    const daemon = new FakeDaemon();
    daemon.routes.set("flights?", "t1");
    const chat = await ChatController.openInChat(daemon, "web", null, board);
    await chat.send("flights?", []);
    expect(chat.getSnapshot().threadId).toBe("t1");
    await chat.send("and hotels?", []);
    expect(daemon.routed).toEqual(["flights?"]);
    expect(daemon.sent).toEqual(["t1: flights?", "t1: and hotels?"]);
  });

  it("keeps the first message where it was written when it goes nowhere else, when it's only files, or when the conversation was picked", async () => {
    const daemon = new FakeDaemon();
    const fresh = await ChatController.openInChat(daemon, "web", null, board);
    await fresh.send("plan my week", []);
    const files = await ChatController.openInChat(daemon, "web", null, board);
    await files.send("", [new File(["hi"], "notes.txt")]);
    const picked = await ChatController.openNew(daemon, "web", board);
    await picked.send("flights?", []);
    expect(daemon.routed).toEqual(["plan my week"]);
    expect(daemon.sent).toEqual(["t2: plan my week", "t2: ", "t2: flights?"]);
  });

  it("sends the first message here when where it goes can't be found out", async () => {
    const daemon = new FakeDaemon();
    daemon.conversations.route = async () => {
      throw new ApiError(500, "no model");
    };
    const chat = await ChatController.openInChat(daemon, "web", null, board);
    await chat.send("flights?", []);
    expect(daemon.sent).toEqual(["t2: flights?"]);
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

  it("stays busy from the inbox's run until the run where its message went has started", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [
      [{ type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Continued in “Trip”." }],
      [{ type: "TextDelta", text: "Two flights." }, { type: "Done" }],
    ];
    const chat = await ChatController.open(daemon, "web", null, board);
    const busy: boolean[] = [];
    chat.subscribe(() => busy.at(-1) !== chat.getSnapshot().busy && busy.push(chat.getSnapshot().busy));
    await chat.send("flights?", []);
    expect(busy).toEqual([false, true, false]);
  });

  it("hands its message on busy until the run there starts, or the handing on ends without one", async () => {
    const daemon = new FakeDaemon();
    const dispatched = { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "?", line: "→ Trip." } as const;
    daemon.runs = [[dispatched], [{ type: "TextDelta", text: "On it." }], [dispatched]];
    const chat = await ChatController.open(daemon, "web", null, board);
    const there = await ChatController.open(daemon, "web", "t1", board);
    const whileHanding: boolean[] = [];
    const whileThere: boolean[] = [];
    there.subscribe(() => texts(there).includes("On it.") && whileThere.push(chat.getSnapshot().busy));
    chat.onDispatched = async () => {
      whileHanding.push(chat.getSnapshot().busy);
      return whileHanding.length === 1 ? there : null;
    };
    await chat.send("a", []);
    await chat.send("b", []);
    expect(whileHanding).toEqual([true, true]);
    expect(whileThere[0]).toBe(false);
    expect(chat.getSnapshot().busy).toBe(false);
  });

  it("writes in the inbox from any conversation, and goes where the message was sent on", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [
      [
        { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Continued in “Trip”." },
        { type: "Done" },
      ],
      [{ type: "TextDelta", text: "Two flights." }, { type: "Done" }],
      [{ type: "TextDelta", text: "Sunny." }, { type: "Done" }],
    ];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await chat.write("flights?", []);
    expect(chat.getSnapshot().threadId).toBe("t1");
    await chat.write("weather?", []);
    expect(daemon.sent).toEqual(["inbox: flights?", "t1: flights? (d1)", "inbox: weather?"]);
    expect(chat.getSnapshot().threadId).toBe("inbox");
    expect(finalReply(chat.getSnapshot().transcript)).toBe("Sunny.");
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
    chat.onDispatched = async (d) => {
      handed.push(d.thread_id);
      return null;
    };
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

  it("shows a task the assistant wrote for its agent as its brief, not as the user's message", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[{ type: "TextDelta", text: "Fixed." }, { type: "Done" }]];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await chat.mirror({ run_id: "r", thread_id: "t1", channel: "web", client_id: "", text: "fix it", brief: "Claude Code" });
    expect(chat.getSnapshot().transcript.items.map((i) => i.kind)).toEqual(["user", "brief", "assistant"]);
    expect(chat.getSnapshot().transcript.items[1]).toMatchObject({ text: "fix it", agent: "Claude Code" });
  });

  it("sends a task the assistant moved out of the inbox as its brief for the agent", async () => {
    const daemon = new FakeDaemon();
    const moved = {
      type: "Dispatched",
      id: "d1",
      thread_id: "",
      title: "Fix",
      text: "fix it",
      line: "→ Moved.",
      brief: "Claude Code",
    } as const;
    daemon.runs = [[moved, { type: "Done" }], [{ type: "Done" }]];
    const chat = await ChatController.open(daemon, "web", null, board);
    await chat.send("fix the tests with claude", []);
    expect(daemon.sent).toEqual(["inbox: fix the tests with claude", "t2: fix it (d1)"]);
    expect(chat.getSnapshot().transcript.items.map((i) => i.kind)).toEqual(["brief"]);
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

describe("ChatController with messages waiting for the reply before them", () => {
  const dispatched = { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Trip." } as const;
  const approval: ApprovalRequired = { type: "ApprovalRequired", interrupt_id: "i1", request: { tool: "bash" } };

  beforeEach(() => {
    board = new NoticeBoard();
  });

  it("sends what the inbox sent on once the run where it went has finished, showing it queued meanwhile", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[approval], [dispatched, { type: "Done" }], [{ type: "Done" }], [{ type: "TextDelta", text: "Two flights." }]];
    const inbox = await ChatController.open(daemon, "web", null, board);
    const there = await ChatController.open(daemon, "web", "t1", board);
    inbox.onDispatched = async () => there;
    const asking = there.send("clean up", []);
    await until(() => there.getSnapshot().approval !== null);
    await inbox.send("flights?", []);
    expect(inbox.getSnapshot().busy).toBe(false);
    expect(there.getSnapshot().queued).toMatchObject([{ text: "flights?", dispatched }]);
    expect(there.unqueue(0)).toBeNull();
    there.answer({ approved: true, reason: null });
    await asking;
    await until(() => finalReply(there.getSnapshot().transcript) === "Two flights.");
    expect(daemon.sent).toEqual(["t1: clean up", "inbox: flights?", "t1: flights? (d1)"]);
    expect(there.getSnapshot().queued).toEqual([]);
  });

  it("sends what was queued in the inbox while it routed after the message, where it went", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[dispatched, { type: "Done" }], [{ type: "Done" }], [{ type: "TextDelta", text: "Three hotels." }]];
    const inbox = await ChatController.open(daemon, "web", null, board);
    const there = await ChatController.open(daemon, "web", "t1", board);
    inbox.onDispatched = async () => there;
    const answered: ChatController[] = [];
    const sent = inbox.send("flights?", []);
    inbox.queue("and hotels?", [], (chat) => answered.push(chat));
    await sent;
    await until(() => answered.length > 0);
    expect(daemon.sent).toEqual(["inbox: flights?", "t1: flights? (d1)", "t1: and hotels?"]);
    expect(answered).toEqual([there]);
    expect(finalReply(there.getSnapshot().transcript)).toBe("Three hotels.");
    expect(inbox.getSnapshot().queued).toEqual([]);
  });

  it("sends a message queued while a run started elsewhere shows once it ends, and at once when nothing runs", async () => {
    const daemon = new FakeDaemon();
    let release = () => {};
    daemon.holding = new Promise((resolve) => (release = resolve));
    daemon.runs = [[{ type: "TextDelta", text: "from telegram" }]];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    const mirrored = chat.mirror({ run_id: "r", thread_id: "t1", channel: "telegram", client_id: "", text: "hi" });
    await until(() => chat.getSnapshot().mirroring);
    chat.queue("next", []);
    expect(daemon.sent).toEqual([]);
    daemon.holding = null;
    release();
    await mirrored;
    await until(() => daemon.sent.length === 1);
    expect(daemon.sent).toEqual(["t1: next"]);
    await until(() => !chat.getSnapshot().busy);
    chat.queue("now", []);
    expect(daemon.sent).toEqual(["t1: next", "t1: now"]);
  });
});

describe("ChatController in a tab with other chats", () => {
  const approval: ApprovalRequired = { type: "ApprovalRequired", interrupt_id: "i1", request: { tool: "bash" } };
  const finished = { run_id: "r", thread_id: "inbox", channel: "telegram", status: "ok", reply: "" };

  beforeEach(() => {
    board = new NoticeBoard();
  });

  it("asks what a run waits on in the chat in Chat, not behind a quick button on the same conversation", async () => {
    const daemon = new FakeDaemon();
    const tab = new ChatTab();
    const chat = await ChatController.open(daemon, "web", null, board, tab);
    const quick = await ChatController.open(daemon, "web", null, board, tab, "quick");
    daemon.waiting.set("inbox", [approval]);
    quick.runFinished(finished);
    chat.runFinished(finished);
    await until(() => chat.getSnapshot().approval !== null);
    await settle();
    expect(quick.getSnapshot().approval).toBeNull();
  });

  it("asks behind a quick button when no chat in Chat is on the conversation", async () => {
    const daemon = new FakeDaemon();
    const tab = new ChatTab();
    const chat = await ChatController.open(daemon, "web", "t1", board, tab);
    const quick = await ChatController.open(daemon, "web", null, board, tab, "quick");
    daemon.waiting.set("inbox", [approval]);
    [chat, quick].forEach((c) => c.runFinished(finished));
    await until(() => quick.getSnapshot().approval !== null);
    expect(chat.getSnapshot().approval).toBeNull();
  });

  it("leaves asking to the chat whose own reply stopped for it", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[approval]];
    const tab = new ChatTab();
    const chat = await ChatController.open(daemon, "web", null, board, tab);
    const quick = await ChatController.open(daemon, "web", null, board, tab, "quick");
    void quick.write("clean up", []);
    await until(() => quick.getSnapshot().approval !== null);
    daemon.waiting.set("inbox", [approval]);
    chat.runFinished(finished);
    await settle();
    expect(chat.getSnapshot()).toMatchObject({ approval: null, busy: false });
  });

  it("hears of a run that starts while its history loads, and shows it after the history", async () => {
    const daemon = new FakeDaemon();
    let loaded = () => {};
    daemon.slowHistory = new Promise((resolve) => (loaded = resolve));
    const tab = new ChatTab();
    const opening = ChatController.open(daemon, "web", "t1", board, tab);
    await until(() => daemon.loading.length > 0);
    daemon.runs = [[{ type: "TextDelta", text: "from telegram" }, { type: "Done" }]];
    tab.all().forEach((c) => c.mirror({ run_id: "r", thread_id: "t1", channel: "telegram", client_id: "", text: "hi" }));
    loaded();
    const chat = await opening;
    await until(() => texts(chat).includes("from telegram"));
    expect(texts(chat)).toEqual(["earlier", "hi", "from telegram"]);
  });

  it("leaves the tab when it's closed", async () => {
    const tab = new ChatTab();
    const chat = await ChatController.open(new FakeDaemon(), "web", "t1", board, tab);
    expect(tab.all()).toEqual([chat]);
    chat.close();
    expect(tab.all()).toEqual([]);
  });
});

describe("ChatController with a run in progress on showing a conversation", () => {
  beforeEach(() => {
    board = new NoticeBoard();
  });

  it("follows it from its start after the history before it, as if the page had been watching", async () => {
    const daemon = new FakeDaemon();
    daemon.inProgress.set("t1", [inProgress("r1", "long task")]);
    daemon.runs = [
      [
        { type: "ToolStarted", name: "bash", args: { command: "make" }, id: "c1" },
        { type: "ToolFinished", name: "bash", output: "built" },
        { type: "TextDelta", text: "Built it." },
        { type: "Done" },
      ],
    ];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => texts(chat).length === 4 && !chat.getSnapshot().mirroring);
    expect(texts(chat)).toEqual(["earlier", "long task", "tool", "Built it."]);
    const [, user, tool] = chat.getSnapshot().transcript.items;
    expect(user).toMatchObject({ kind: "user", channel: undefined });
    expect(tool).toMatchObject({ state: "done", output: "built" });
  });

  it("shows the events that came at once in one update, never the run half shown", async () => {
    const daemon = new FakeDaemon();
    daemon.inProgress.set("t1", [inProgress("r1", "long task")]);
    daemon.runs = [
      [
        { type: "ToolStarted", name: "bash", args: { command: "make" }, id: "c1" },
        { type: "ToolFinished", name: "bash", output: "built" },
        { type: "TextDelta", text: "Built " },
        { type: "TextDelta", text: "it." },
        { type: "Done" },
      ],
    ];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    const seen: string[][] = [];
    chat.subscribe(() => seen.push(texts(chat)));
    await until(() => texts(chat).length === 4 && !chat.getSnapshot().mirroring);
    const shownRun = seen.filter((shown) => shown.length > 2);
    expect(shownRun.every((shown) => shown.join("|") === "earlier|long task|tool|Built it.")).toBe(true);
  });

  it("follows the runs in progress one after another, each after what started it", async () => {
    const daemon = new FakeDaemon();
    daemon.inProgress.set("t1", [inProgress("r1", "first?", ""), inProgress("r2", "second?")]);
    daemon.runs = [
      [{ type: "TextDelta", text: "First." }, { type: "Done" }],
      [{ type: "TextDelta", text: "Second." }, { type: "Done" }],
    ];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => texts(chat).length === 5);
    expect(texts(chat)).toEqual(["earlier", "first?", "First.", "second?", "Second."]);
    expect(chat.getSnapshot().transcript.items[1]).toMatchObject({ channel: "telegram" });
  });

  it("shows it once when its run event comes too", async () => {
    const daemon = new FakeDaemon();
    const run = inProgress("r1", "hi", "");
    daemon.inProgress.set("t1", [run]);
    daemon.runs = [[{ type: "TextDelta", text: "working" }]];
    daemon.keepOpen = true;
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => texts(chat).includes("working"));
    await chat.mirror(run);
    expect(daemon.followed).toEqual(["r1"]);
    expect(texts(chat)).toEqual(["earlier", "hi", "working"]);
  });

  it("shows a run announced while the history loads after it, unless it's among the runs in progress", async () => {
    const daemon = new FakeDaemon();
    daemon.saved.add("t3");
    const chat = await ChatController.open(daemon, "web", "t1", board);
    let loaded = () => {};
    daemon.slowHistory = new Promise((resolve) => (loaded = resolve));
    const listed = { ...inProgress("r1", "listed", ""), thread_id: "t3" };
    daemon.inProgress.set("t3", [listed]);
    daemon.runs = [[{ type: "Done" }], [{ type: "Done" }]];
    const resumed = chat.resume("t3");
    await until(() => daemon.loading.includes("t3"));
    const announced = chat.mirror({ ...listed, run_id: "r2", text: "announced" });
    const again = chat.mirror(listed);
    loaded();
    await Promise.all([resumed, announced, again]);
    await until(() => !chat.getSnapshot().mirroring);
    expect(daemon.followed.sort()).toEqual(["r1", "r2"]);
    expect(texts(chat)).toEqual(["earlier", "listed", "announced"]);
  });

  it("stops following when the page goes to another conversation, and follows again on coming back", async () => {
    const daemon = new FakeDaemon();
    daemon.saved.add("t3");
    daemon.inProgress.set("t1", [inProgress("r1", "a"), inProgress("r2", "b")]);
    daemon.runs = [[{ type: "TextDelta", text: "working" }], [{ type: "TextDelta", text: "working again" }]];
    daemon.keepOpen = true;
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => texts(chat).includes("working"));
    await chat.resume("t3");
    await settle();
    expect(chat.getSnapshot()).toMatchObject({ threadId: "t3", mirroring: false });
    expect(texts(chat)).toEqual(["earlier"]);
    expect(daemon.followed).toEqual(["r1"]);
    await chat.resume("t1");
    await until(() => texts(chat).includes("working again"));
    expect(texts(chat)).toEqual(["earlier", "a", "working again"]);
    expect(chat.getSnapshot().mirroring).toBe(true);
  });
});

describe("ChatController with a run waiting for the user", () => {
  const approval: ApprovalRequired = { type: "ApprovalRequired", interrupt_id: "i1", request: { tool: "mcp__factory__approve" } };
  const resumed: RunEvent[] = [{ type: "TextDelta", text: "approved it" }, { type: "Done" }];

  beforeEach(() => {
    board = new NoticeBoard();
  });

  it("asks on opening a conversation whose run waits, as after a reload, and goes on with the answer", async () => {
    const daemon = new FakeDaemon();
    daemon.waiting.set("t1", [approval]);
    daemon.runs = [resumed];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => chat.getSnapshot().approval !== null);
    expect(chat.getSnapshot()).toMatchObject({ approval, busy: true });
    chat.answer({ approved: true, reason: null });
    await until(() => !chat.getSnapshot().busy);
    expect(daemon.decisions).toEqual([{ i1: { approved: true, reason: null } }]);
    expect(chat.getSnapshot().approval).toBeNull();
    expect(texts(chat)).toEqual(["earlier", "approved it"]);
  });

  it("asks what a run started elsewhere stopped for, once it ends", async () => {
    const daemon = new FakeDaemon();
    daemon.runs = [[{ type: "ToolStarted", name: "mcp__factory__approve", args: {} }, approval], resumed];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await chat.mirror({ run_id: "r", thread_id: "t1", channel: "worker", client_id: "", text: "" });
    expect(chat.getSnapshot().approval).toBeNull();
    daemon.waiting.set("t1", [approval]);
    chat.runFinished({ run_id: "r", thread_id: "t1", channel: "worker", status: "ok", reply: "" });
    await until(() => chat.getSnapshot().approval !== null);
    chat.answer({ approved: false, reason: "no" });
    await until(() => !chat.getSnapshot().busy);
    expect(daemon.decisions).toEqual([{ i1: { approved: false, reason: "no" } }]);
  });

  it("asks on going back to a conversation whose run waits, and not for another conversation's", async () => {
    const daemon = new FakeDaemon();
    daemon.saved.add("t3");
    daemon.waiting.set("t3", [approval]);
    const chat = await ChatController.open(daemon, "web", "t1", board);
    chat.runFinished({ run_id: "r", thread_id: "t3", channel: "web", status: "ok", reply: "" });
    await settle();
    expect(chat.getSnapshot().approval).toBeNull();
    await chat.resume("t3");
    await until(() => chat.getSnapshot().approval !== null);
  });

  it("stops asking once another client answers and goes on with the run", async () => {
    const daemon = new FakeDaemon();
    daemon.waiting.set("t1", [approval]);
    daemon.runs = [resumed];
    const chat = await ChatController.open(daemon, "web", "t1", board);
    await until(() => chat.getSnapshot().approval !== null);
    daemon.waiting.delete("t1");
    await chat.mirror({ run_id: "r", thread_id: "t1", channel: "telegram", client_id: "", text: "" });
    expect(chat.getSnapshot()).toMatchObject({ approval: null, busy: false });
    expect(daemon.decisions).toEqual([]);
    expect(texts(chat)).toEqual(["earlier", "approved it"]);
    expect(board.getSnapshot()).toEqual([]);
  });
});

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i++) await new Promise((resolve) => setTimeout(resolve, 0));
}

async function until(condition: () => boolean): Promise<void> {
  for (let i = 0; i < 100 && !condition(); i++) await new Promise((resolve) => setTimeout(resolve, 0));
  expect(condition()).toBe(true);
}
