import { describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import type { ApprovalRequired, Dispatched, RunEvent, Session } from "../api/types";
import { NoticeBoard } from "../notices";
import type { ChatClient } from "./controller";
import { OpenChats } from "./openChats";
import { openList } from "./openList";

/** The daemon as each open conversation's client sees it, recording which client is on which conversation. */
class Daemon {
  saved = new Set(["t1", "t2"]);
  // What each send plays, in order; nothing when none is left.
  runs: RunEvent[][] = [];
  sent: string[] = [];
  on = new Map<string, string>();
  left: string[] = [];
  // What each conversation's run stopped for and waits on.
  waiting = new Map<string, ApprovalRequired[]>();
  // Where a new conversation's first message goes; "" for where it was written.
  routes = new Map<string, string>();
  private next = 10;

  clientFor = (part: string | null): ChatClient => {
    const id = part ?? "me";
    const play = async function* (this: Daemon): AsyncGenerator<RunEvent> {
      yield* this.runs.shift() ?? [];
    }.bind(this);
    return {
      clientId: id,
      inboxThread: async () => this.move(id, "inbox"),
      newThread: async () => this.move(id, `t${this.next++}`),
      resumeThread: async (threadId: string) => {
        if (!this.saved.has(threadId)) throw new ApiError(404, "gone");
        this.move(id, threadId);
      },
      leaveThread: async () => {
        this.left.push(this.on.get(id) ?? "");
        this.on.delete(id);
      },
      send: (session: Session, text: string) => {
        this.sent.push(`${session.thread_id}: ${text}`);
        return play();
      },
      sendDispatched: (session: Session, dispatched: Dispatched) => {
        this.sent.push(`${session.thread_id}: ${dispatched.id}`);
        return play();
      },
      moveDispatched: (session: Session, id: string) => {
        this.sent.push(`${session.thread_id}: move ${id}`);
        return play();
      },
      resume: () => play(),
      followRunBatches: async function* (): AsyncGenerator<RunEvent[]> {},
      cancel: async () => true,
      conversations: {
        live: async () => ({ messages: [], runs: [] }),
        approvals: async (threadId: string) => this.waiting.get(threadId) ?? [],
        route: async (text: string) => this.routes.get(text) ?? "",
      },
    };
  };

  private move(id: string, threadId: string): string {
    this.on.set(id, threadId);
    return threadId;
  }
}

const approval = (id: string): ApprovalRequired => ({ type: "ApprovalRequired", interrupt_id: id, request: { tool: "bash" } });
const waiting = (chats: OpenChats) =>
  openList(chats.getSnapshot(), [], [])
    .filter((item) => item.waiting)
    .map((item) => item.threadId);
const settled = () => new Promise((resolve) => setTimeout(resolve, 0));
const threads = (chats: OpenChats) => chats.all().map((c) => c.getSnapshot().threadId);
const shown = (chats: OpenChats) => chats.current?.getSnapshot().threadId ?? null;
const open = (daemon: Daemon, saved: (string | null)[], active = 0) =>
  OpenChats.open(daemon.clientFor, "web", saved, active, new NoticeBoard());

describe("OpenChats", () => {
  it("reopens the conversations open before a reload, each under a client of its own", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t1", "t2"], 1);
    expect(threads(chats)).toEqual(["t1", "t2"]);
    expect(shown(chats)).toBe("t2");
    const [own, part] = [...daemon.on.entries()];
    expect(own).toEqual(["me", "t1"]);
    expect(part[0]).not.toBe("me");
    expect(part[1]).toBe("t2");
    expect(chats.saved()).toEqual({ threads: ["t1", "t2"], active: 1 });
  });

  it("never opens the inbox: a new conversation for a new tab, for one gone, and for the inbox", async () => {
    expect(threads(await open(new Daemon(), [null]))).toEqual(["t10"]);
    const daemon = new Daemon();
    daemon.saved.add("inbox");
    expect(threads(await open(daemon, ["gone", "inbox", "t1"]))).toEqual(["t10", "t11", "t1"]);
  });

  it("shows nothing for the inbox, which Chat never shows, nor for a conversation that's gone", async () => {
    const daemon = new Daemon();
    daemon.saved.add("inbox");
    const chats = await open(daemon, ["t1"]);
    expect(chats.inboxId).toBe("inbox");
    expect(await chats.show("inbox")).toBe("inbox");
    expect(await chats.show("deleted")).toBe("gone");
    expect(threads(chats)).toEqual(["t1"]);
    expect(await chats.show("t2")).toBe("shown");
    expect(threads(chats)).toEqual(["t1", "t2"]);
  });

  it("sends a fresh conversation's first message to the open one it continues, closing the fresh one", async () => {
    const daemon = new Daemon();
    daemon.routes.set("flights?", "t1");
    const chats = await open(daemon, ["t1", "gone"], 1);
    expect(threads(chats)).toEqual(["t1", "t10"]);
    await chats.current?.send("flights?", []);
    expect(threads(chats)).toEqual(["t1"]);
    expect(shown(chats)).toBe("t1");
    expect(daemon.sent).toEqual(["t1: flights?"]);
  });

  it("moves a fresh conversation to the one its first message continues when that isn't open", async () => {
    const daemon = new Daemon();
    daemon.routes.set("flights?", "t2");
    const chats = await open(daemon, [null]);
    await chats.current?.send("flights?", []);
    expect(threads(chats)).toEqual(["t2"]);
    expect(daemon.sent).toEqual(["t2: flights?"]);
  });

  it("starts a new conversation beside the others and shows it", async () => {
    const chats = await open(new Daemon(), ["t1"]);
    const started = await chats.startNew();
    expect(threads(chats)).toEqual(["t1", "t10"]);
    expect(chats.current).toBe(started);
  });

  it("shows a conversation already open, and opens any other beside the rest", async () => {
    const chats = await open(new Daemon(), ["t1", "t2"]);
    await chats.show("t2");
    expect(threads(chats)).toEqual(["t1", "t2"]);
    expect(shown(chats)).toBe("t2");
    await chats.startNew();
    await chats.show("t1");
    expect(shown(chats)).toBe("t1");
  });

  it("moves a message in the inbox without showing it, asking over Chat, and opens where it goes", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t2"]);
    const question: ApprovalRequired = { type: "ApprovalRequired", interrupt_id: "q1", request: { kind: "question" } };
    daemon.runs = [
      [question],
      [
        { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Moved “flights?” to “Trip”." },
        { type: "Done" },
      ],
    ];
    const moving = chats.move("");
    await settled();
    expect(chats.getSnapshot().moving).toEqual(question);
    expect(threads(chats)).toEqual(["t2"]);
    chats.answerMove({ choices: ["Trip"] });
    await moving;
    expect(chats.getSnapshot().moving).toBeNull();
    expect(threads(chats)).toEqual(["t2", "t1"]);
    expect(shown(chats)).toBe("t1");
    expect(daemon.sent).toEqual(["inbox: move ", "t1: d1"]);
    expect(daemon.left).toEqual(["inbox"]);
  });

  it("sends a moved message to an open conversation once what it asks is answered, queued meanwhile", async () => {
    const daemon = new Daemon();
    daemon.waiting.set("t1", [approval("i1")]);
    const chats = await open(daemon, ["t2", "t1"], 0);
    const trip = chats.all()[1];
    await settled();
    expect(trip.getSnapshot().approval).not.toBeNull();
    daemon.runs = [
      [{ type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Moved “flights?” to “Trip”." }],
    ];
    await chats.move("");
    expect(chats.current).toBe(trip);
    expect(trip.getSnapshot().queued).toMatchObject([{ text: "flights?" }]);
    expect(daemon.sent).toEqual(["inbox: move "]);
    trip.answer({ approved: true, reason: null });
    await settled();
    expect(daemon.sent).toEqual(["inbox: move ", "t1: d1"]);
    expect(trip.getSnapshot().queued).toEqual([]);
  });

  it("closes one and leaves it in the daemon, shows the next, and closes the last too", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t1", "t2"], 0);
    const [first, second] = chats.getSnapshot().chats.map((c) => c.key);
    await chats.close(first);
    expect(daemon.left).toEqual(["t1"]);
    expect(threads(chats)).toEqual(["t2"]);
    expect(chats.getSnapshot().activeKey).toBe(second);
    await chats.close(second);
    expect(daemon.left).toEqual(["t1", "t2"]);
    expect(threads(chats)).toEqual([]);
    expect(chats.current).toBeNull();
    expect(chats.getSnapshot().activeKey).toBeNull();
    expect(chats.saved()).toEqual({ threads: [], active: -1 });
  });

  it("starts or shows a conversation again after the last one closed", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t1"]);
    await chats.close(chats.getSnapshot().chats[0].key);
    expect(chats.inboxId).toBe("inbox");
    expect(await chats.show("inbox")).toBe("inbox");
    const started = await chats.startNew();
    expect(chats.current).toBe(started);
    expect(await chats.show("t2")).toBe("shown");
    expect(threads(chats)).toEqual(["t10", "t2"]);
    expect(shown(chats)).toBe("t2");
  });

  it("reopens none when none was open before a reload, knowing the inbox all the same", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, [], 0);
    expect(threads(chats)).toEqual([]);
    expect(chats.current).toBeNull();
    expect(chats.getSnapshot().activeKey).toBeNull();
    expect(chats.inboxId).toBe("inbox");
    expect(await chats.show("t1")).toBe("shown");
    expect(shown(chats)).toBe("t1");
  });

  it("marks an open conversation not shown that waits for an answer, on opening and when a run there stops for one", async () => {
    const daemon = new Daemon();
    daemon.waiting.set("t2", [approval("i1")]);
    const chats = await open(daemon, ["t1", "t2"], 0);
    await settled();
    expect(shown(chats)).toBe("t1");
    expect(waiting(chats)).toEqual(["t2"]);
    daemon.saved.add("t3");
    await chats.show("t3");
    chats.activate(chats.getSnapshot().chats[0].key);
    daemon.waiting.set("t3", [approval("i2")]);
    chats.all().forEach((chat) => chat.runFinished({ run_id: "r", thread_id: "t3", channel: "telegram", status: "ok", reply: "" }));
    await settled();
    expect(waiting(chats)).toEqual(["t2", "t3"]);
  });
});
