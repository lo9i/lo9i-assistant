import { describe, expect, it, vi } from "vitest";
import { ConversationsGroup, JobsGroup, SystemGroup } from "./client";
import type { Transport } from "./transport";

function recording(): { transport: Transport; request: ReturnType<typeof vi.fn> } {
  const request = vi.fn().mockResolvedValue({ ok: true });
  return { transport: { clientId: "c", request, blob: vi.fn(), stream: vi.fn() }, request };
}

describe("ConversationsGroup.messageAgent", () => {
  it("sends the text and each file as a form, as a chat message is sent", async () => {
    const { transport, request } = recording();
    const shot = new File(["png"], "shot.png", { type: "image/png" });
    await new ConversationsGroup(transport).messageAgent("t 1", "see this", [shot]);
    const [method, path, form] = request.mock.calls[0] as [string, string, FormData];
    expect([method, path]).toEqual(["POST", "/conversations/t%201/agent/messages"]);
    expect(form.get("text")).toBe("see this");
    expect((form.getAll("files") as File[]).map((f) => f.name)).toEqual(["shot.png"]);
  });

  it("sends files alone", async () => {
    const { transport, request } = recording();
    await new ConversationsGroup(transport).messageAgent("t", "", [new File(["x"], "a.txt")]);
    const form = request.mock.calls[0][2] as FormData;
    expect(form.get("text")).toBe("");
    expect(form.getAll("files")).toHaveLength(1);
  });
});

describe("ConversationsGroup.childFolders", () => {
  it("leaves hidden folders out unless asked for them", async () => {
    const { transport, request } = recording();
    const conversations = new ConversationsGroup(transport);
    await conversations.childFolders("/Users/me");
    await conversations.childFolders("/Users/me", true);
    expect(request.mock.calls.map((call) => call[1])).toEqual([
      "/agents/folders/children?path=%2FUsers%2Fme",
      "/agents/folders/children?path=%2FUsers%2Fme&hidden=true",
    ]);
  });
});

describe("ConversationsGroup.toolCall", () => {
  it("asks for the call by its id in its conversation", async () => {
    const { transport, request } = recording();
    await new ConversationsGroup(transport).toolCall("owner:t 1", "toolu/1");
    expect(request.mock.calls[0].slice(0, 2)).toEqual(["GET", "/conversations/owner%3At%201/tool-calls/toolu%2F1"]);
  });
});

describe("JobsGroup.runReply", () => {
  it("asks for the run by when it started and returns its whole reply", async () => {
    const { transport, request } = recording();
    request.mockResolvedValue({ text: "The whole reply." });
    const text = await new JobsGroup(transport).runReply("daily news", "2026-10-24T09:00:00+00:00");
    expect(request.mock.calls[0].slice(0, 2)).toEqual(["GET", "/jobs/daily%20news/reply?at=2026-10-24T09%3A00%3A00%2B00%3A00"]);
    expect(text).toBe("The whole reply.");
  });
});

describe("SystemGroup's pending ending", () => {
  it("reads it, takes it back, and makes it go ahead now", async () => {
    const { transport, request } = recording();
    const system = new SystemGroup(transport);
    await system.ending();
    await system.takeBackEnding();
    request.mockResolvedValue({ cancelled: 2 });
    expect(await system.endNow()).toBe(2);
    expect(request.mock.calls.map((call) => call.slice(0, 2))).toEqual([
      ["GET", "/system/ending"],
      ["DELETE", "/system/ending"],
      ["POST", "/system/ending/now"],
    ]);
  });
});
