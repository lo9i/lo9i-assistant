import { describe, expect, it } from "vitest";
import { addUser, apply, empty } from "./chat/transcript";
import { finalReply } from "./chat/transcript";
import { speaksReply } from "./speech";

describe("spoken replies", () => {
  it("speak when the setting says so", () => {
    expect(speaksReply("always", false)).toBe(true);
    expect(speaksReply("voice", true)).toBe(true);
    expect(speaksReply("voice", false)).toBe(false);
    expect(speaksReply("off", true)).toBe(false);
    expect(speaksReply(undefined, true)).toBe(false);
  });

  it("read only the answer after the last tool call", () => {
    let t = addUser(empty, "weather?", []);
    t = apply(t, { type: "TextDelta", text: "Let me check." });
    t = apply(t, { type: "ToolStarted", name: "web_search", args: {} });
    t = apply(t, { type: "TextDelta", text: "It's sunny." });
    expect(finalReply(t)).toBe("It's sunny.");
  });
});
