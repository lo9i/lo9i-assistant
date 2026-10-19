import { describe, expect, it } from "vitest";
import { ApiError } from "../api/errors";
import type { RunEvent, Session } from "../api/types";
import { NoticeBoard } from "../notices";
import type { ChatClient } from "./controller";
import { OpenChats } from "./openChats";

/** The daemon as each open conversation's client sees it, recording which client is on which conversation. */
class Daemon {
  saved = new Set(["t1", "t2"]);
  // What each send plays, in order; nothing when none is left.
  runs: RunEvent[][] = [];
  sent: string[] = [];
  on = new Map<string, string>();
  left: string[] = [];
  private next = 10;

  clientFor = (part: string | null): ChatClient => {
    const id = part ?? "me";
    const empty = async function* (): AsyncGenerator<RunEvent> {};
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
      sendDispatched: (session: Session, id: string) => {
        this.sent.push(`${session.thread_id}: ${id}`);
        return play();
      },
      moveDispatched: (session: Session, id: string) => {
        this.sent.push(`${session.thread_id}: move ${id}`);
        return play();
      },
      resume: empty,
      followRun: empty,
      cancel: async () => true,
      conversations: { messages: async () => [] },
    };
  };

  private move(id: string, threadId: string): string {
    this.on.set(id, threadId);
    return threadId;
  }
}

const threads = (chats: OpenChats) => chats.all().map((c) => c.getSnapshot().threadId);
const open = (daemon: Daemon, saved: string[], active = 0) => OpenChats.open(daemon.clientFor, "web", saved, active, new NoticeBoard());

describe("OpenChats", () => {
  it("reopens the conversations open before a reload, each under a client of its own", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t1", "t2"], 1);
    expect(threads(chats)).toEqual(["t1", "t2"]);
    expect(chats.current.getSnapshot().threadId).toBe("t2");
    const [own, part] = [...daemon.on.entries()];
    expect(own).toEqual(["me", "t1"]);
    expect(part[0]).not.toBe("me");
    expect(part[1]).toBe("t2");
    expect(chats.saved()).toEqual({ threads: ["t1", "t2"], active: 1 });
  });

  it("opens the inbox when nothing was open, and keeps one of two that both came back as the inbox", async () => {
    expect(threads(await open(new Daemon(), []))).toEqual(["inbox"]);
    const daemon = new Daemon();
    expect(threads(await open(daemon, ["gone", "lost"]))).toEqual(["inbox"]);
    expect(daemon.left).toEqual(["inbox"]);
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
    expect(chats.current.getSnapshot().threadId).toBe("t2");
    await chats.startNew();
    await chats.show("t1");
    expect(chats.current.getSnapshot().threadId).toBe("t1");
  });

  it("goes to the open inbox, or opens it beside the others", async () => {
    const chats = await open(new Daemon(), ["inbox", "t1"], 1);
    await chats.goInbox();
    expect(threads(chats)).toEqual(["inbox", "t1"]);
    expect(chats.current.getSnapshot().threadId).toBe("inbox");
    const alone = await open(new Daemon(), ["t1"]);
    await alone.goInbox();
    expect(threads(alone)).toEqual(["t1", "inbox"]);
    expect(alone.current.getSnapshot().threadId).toBe("inbox");
  });

  it("writes a message from the inbox and opens where it went", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t2"]);
    daemon.runs = [
      [
        { type: "Dispatched", id: "d1", thread_id: "", title: "New conversation", text: "plan", line: "→ Started a new conversation." },
        { type: "Done" },
      ],
    ];
    await chats.write("plan", []);
    expect(threads(chats)).toEqual(["t2", "inbox", "t10"]);
    expect(chats.current.getSnapshot().threadId).toBe("t10");
    expect(daemon.sent).toEqual(["inbox: plan", "t10: d1"]);
  });

  it("opens where the inbox sent a message on beside it, and sends it there", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, []);
    daemon.runs = [
      [
        { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Continued in “Trip”." },
        { type: "Done" },
      ],
    ];
    await chats.current.send("flights?", []);
    expect(threads(chats)).toEqual(["inbox", "t1"]);
    expect(chats.current.getSnapshot().threadId).toBe("t1");
    expect(daemon.sent).toEqual(["inbox: flights?", "t1: d1"]);
  });

  it("moves a message from the inbox, showing the inbox first, and opens where it goes", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t2"]);
    daemon.runs = [
      [
        { type: "Dispatched", id: "d1", thread_id: "t1", title: "Trip", text: "flights?", line: "→ Moved “flights?” to “Trip”." },
        { type: "Done" },
      ],
    ];
    await chats.move("");
    expect(threads(chats)).toEqual(["t2", "inbox", "t1"]);
    expect(daemon.sent).toEqual(["inbox: move ", "t1: d1"]);
  });

  it("closes one and leaves it in the daemon, shows the next, and keeps the last", async () => {
    const daemon = new Daemon();
    const chats = await open(daemon, ["t1", "t2"], 0);
    const [first, second] = chats.getSnapshot().chats.map((c) => c.key);
    await chats.close(first);
    expect(daemon.left).toEqual(["t1"]);
    expect(threads(chats)).toEqual(["t2"]);
    expect(chats.getSnapshot().activeKey).toBe(second);
    await chats.close(second);
    expect(threads(chats)).toEqual(["t2"]);
  });
});
