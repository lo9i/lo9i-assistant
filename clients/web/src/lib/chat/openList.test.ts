import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import type { ChatSnapshot } from "./controller";
import { openList } from "./openList";
import { empty } from "./transcript";

const state = (threadId: string, change: Partial<ChatSnapshot> = {}): ChatSnapshot => ({
  threadId,
  inboxId: "inbox",
  transcript: empty,
  busy: false,
  mirroring: false,
  approval: null,
  queued: [],
  ...change,
});
const conversation = (thread_id: string, title: string, inbox = false) => ({ thread_id, title, inbox }) as Conversation;

describe("openList", () => {
  it("lists the open conversations, then others with something working, with what each is doing", () => {
    const open = {
      chats: [
        { key: "", state: state("inbox") },
        { key: "a", state: state("t1", { busy: true }) },
        { key: "b", state: state("t2", { approval: {} as ChatSnapshot["approval"] }) },
        { key: "c", state: state("t9") },
      ],
      activeKey: "a",
    };
    const conversations = [
      conversation("inbox", "Quick questions", true),
      conversation("t1", "Trip"),
      conversation("t2", "Taxes"),
      conversation("t3", "Calendar"),
    ];
    const items = openList(open, conversations, ["t3", "t2", "job:x"]);
    expect(items.map((i) => [i.key, i.title, i.active, i.running, i.waiting])).toEqual([
      ["a", "Trip", true, true, false],
      ["b", "Taxes", false, true, true],
      ["c", "New conversation", false, false, false],
      [null, "Calendar", false, true, false],
    ]);
  });

  it("leaves the inbox out, open here or working elsewhere", () => {
    const open = { chats: [{ key: "a", state: state("t1") }], activeKey: "a" };
    const conversations = [conversation("inbox", "Quick questions", true), conversation("t1", "Trip")];
    expect(openList(open, conversations, ["inbox"]).map((i) => i.threadId)).toEqual(["t1"]);
    const shown = { chats: [{ key: "", state: state("inbox", { busy: true }) }], activeKey: "" };
    expect(openList(shown, conversations, [])).toEqual([]);
  });
});
