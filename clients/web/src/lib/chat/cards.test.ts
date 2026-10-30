import { describe, expect, it } from "vitest";
import type { ApprovalRequired } from "../api/types";
import { cardStatus, lastMessages } from "./cards";
import type { ChatItem } from "./transcript";

const approval: ApprovalRequired = { type: "ApprovalRequired", interrupt_id: "i", request: { tool: "bash" } };
const idle = { busy: false, mirroring: false, approval: null };

describe("cardStatus", () => {
  it("says a question or approval waits for the user before anything else", () => {
    expect(cardStatus({ ...idle, busy: true, approval }, true, false)).toBe("waiting");
    expect(cardStatus(null, true, true)).toBe("waiting");
  });

  it("goes by this tab's chat on it, when there is one, for what waits", () => {
    expect(cardStatus(idle, false, true)).toBe("idle");
  });

  it("says it works while a reply or task runs, here or anywhere", () => {
    expect(cardStatus({ ...idle, busy: true }, false, false)).toBe("working");
    expect(cardStatus({ ...idle, mirroring: true }, false, false)).toBe("working");
    expect(cardStatus(null, true, false)).toBe("working");
    expect(cardStatus(null, false, false)).toBe("idle");
  });
});

describe("lastMessages", () => {
  const items: ChatItem[] = [
    { kind: "user", id: 1, text: "first", files: [] },
    { kind: "assistant", id: 2, text: "reply one" },
    { kind: "user", id: 3, text: "", files: ["a.png"] },
    { kind: "assistant", id: 4, text: "Looking." },
    { kind: "tool", id: 5, name: "bash", state: "done" },
    { kind: "assistant", id: 6, text: "Found it. <!-- choices: Yes | No -->" },
    { kind: "brief", id: 7, text: "Fix the tests", agent: "Claude" },
    { kind: "assistant", id: 8, text: "  " },
  ];

  it("takes the last messages with text, a reply split by tool calls as one, without answer buttons", () => {
    expect(lastMessages(items, 3)).toEqual([
      { id: 3, from: "user", text: "a.png" },
      { id: 4, from: "assistant", text: "Looking.\n\nFound it." },
      { id: 7, from: "agent", text: "Fix the tests" },
    ]);
  });

  it("takes them all when there are fewer", () => {
    expect(lastMessages(items.slice(0, 2), 5).map((e) => e.text)).toEqual(["first", "reply one"]);
    expect(lastMessages([], 3)).toEqual([]);
  });
});
