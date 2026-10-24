import { describe, expect, it, vi } from "vitest";
import { ConversationsGroup } from "./client";
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
