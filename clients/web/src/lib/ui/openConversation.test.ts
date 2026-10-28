import { beforeEach, describe, expect, it, vi } from "vitest";
import { NoticeBoard } from "$lib/notices";

const goto = vi.fn();
vi.mock("$app/navigation", () => ({ goto }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));

const { leaveInbox, openConversation } = await import("./openConversation");

describe("openConversation", () => {
  beforeEach(() => goto.mockClear());

  it("opens a conversation in Chat, and goes to the list for the inbox, which Chat never shows", async () => {
    const chats = { show: async (threadId: string) => threadId !== "inbox" };
    await openConversation(chats, new NoticeBoard(), "t1");
    await openConversation(chats, new NoticeBoard(), "inbox");
    expect(goto.mock.calls).toEqual([["/app/conversations/open"], ["/app/conversations"]]);
  });
});

describe("leaveInbox", () => {
  beforeEach(() => goto.mockClear());

  it("replaces a page about to show the inbox with the list of conversations", () => {
    expect(leaveInbox({ threadId: "inbox", inboxId: "inbox" })).toBe(true);
    expect(goto.mock.calls).toEqual([["/app/conversations", { replaceState: true }]]);
  });

  it("stays on any other conversation", () => {
    expect(leaveInbox({ threadId: "t1", inboxId: "inbox" })).toBe(false);
    expect(goto).not.toHaveBeenCalled();
  });
});
