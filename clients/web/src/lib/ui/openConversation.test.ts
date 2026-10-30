import { beforeEach, describe, expect, it, vi } from "vitest";
import { besideOf, initial, together, type Layout } from "$lib/chat/cardLayout";
import type { Shown } from "$lib/chat/openChats";
import { NoticeBoard } from "$lib/notices";

const goto = vi.fn();
vi.mock("$app/navigation", () => ({ goto }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));

const { leaveInbox, openBeside, openConversation, startNewHere } = await import("./openConversation");

describe("openConversation", () => {
  beforeEach(() => goto.mockClear());

  it("opens a conversation in Chat, and goes to the list for the inbox, which Chat never shows", async () => {
    const chats = { show: async (threadId: string) => (threadId === "inbox" ? "inbox" : "shown") as Shown };
    await openConversation(chats, new NoticeBoard(), "t1");
    await openConversation(chats, new NoticeBoard(), "inbox");
    expect(goto.mock.calls).toEqual([["/app/conversations/open"], ["/app/conversations"]]);
  });

  it("says a conversation that was deleted is gone, staying on the page", async () => {
    const notices = new NoticeBoard();
    await openConversation({ show: async () => "gone" as Shown }, notices, "t1");
    expect(goto).not.toHaveBeenCalled();
    expect(notices.getSnapshot().map((n) => n.text)).toEqual(["That conversation was deleted."]);
  });
});

describe("leaveInbox", () => {
  beforeEach(() => goto.mockClear());

  it("replaces a page about to show the inbox with the list of conversations", () => {
    expect(leaveInbox({ threadId: "inbox", inboxId: "inbox" })).toBe(true);
    expect(goto.mock.calls).toEqual([["/app/conversations", { replaceState: true }]]);
  });

  it("replaces a page about to show no conversation, none being open, with the list", () => {
    expect(leaveInbox(null)).toBe(true);
    expect(goto.mock.calls).toEqual([["/app/conversations", { replaceState: true }]]);
  });

  it("stays on any other conversation", () => {
    expect(leaveInbox({ threadId: "t1", inboxId: "inbox" })).toBe(false);
    expect(goto).not.toHaveBeenCalled();
  });
});

describe("openBeside", () => {
  beforeEach(() => goto.mockClear());

  const shownOn = (threadId: string | null) => ({
    current: threadId === null ? null : ({ getSnapshot: () => ({ threadId, inboxId: "inbox" }) } as never),
  });

  function columns() {
    let current = initial;
    return {
      get current() {
        return current;
      },
      change: (next: Layout) => void (current = next),
    };
  }

  it("opens a conversation beside the one shown, as columns of the conversation page", async () => {
    const kept = columns();
    await openBeside({ ...shownOn("t1"), show: async () => "shown" as Shown }, new NoticeBoard(), kept, "t2");
    expect(together(kept.current)).toEqual(["t1", "t2"]);
    expect(goto.mock.calls).toEqual([["/app/conversations/open"]]);
  });

  it("opens it alone when none is shown, or the inbox is", async () => {
    const kept = columns();
    await openBeside({ ...shownOn(null), show: async () => "shown" as Shown }, new NoticeBoard(), kept, "t2");
    await openBeside({ ...shownOn("inbox"), show: async () => "shown" as Shown }, new NoticeBoard(), kept, "t2");
    expect(together(kept.current)).toEqual([]);
  });

  it("leaves the columns alone for one that was deleted, and says so", async () => {
    const kept = columns();
    const notices = new NoticeBoard();
    await openBeside({ ...shownOn("t1"), show: async () => "gone" as Shown }, notices, kept, "t2");
    expect(together(kept.current)).toEqual([]);
    expect(goto).not.toHaveBeenCalled();
    expect(notices.getSnapshot().map((n) => n.text)).toEqual(["That conversation was deleted."]);
  });
});

describe("startNewHere", () => {
  const chatOn = (threadId: string) => ({ getSnapshot: () => ({ threadId, inboxId: "inbox" }) }) as never;

  function columns(start: Layout) {
    let current = start;
    return {
      get current() {
        return current;
      },
      change: (next: Layout) => void (current = next),
    };
  }

  it("adds the new conversation to the ones side by side with the one shown", async () => {
    const kept = columns(besideOf(initial, "a", "b"));
    await startNewHere({ current: chatOn("a"), startNew: async () => chatOn("n") }, kept);
    expect(together(kept.current)).toEqual(["a", "b", "n"]);
  });

  it("shows it alone when the one shown is alone", async () => {
    const kept = columns(besideOf(initial, "a", "b"));
    await startNewHere({ current: chatOn("x"), startNew: async () => chatOn("n") }, kept);
    await startNewHere({ current: null, startNew: async () => chatOn("m") }, kept);
    expect(together(kept.current)).toEqual(["a", "b"]);
  });
});
