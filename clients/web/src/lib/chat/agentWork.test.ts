import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { putBack, tellAgent } from "./agentWork";

describe("tellAgent", () => {
  it("passes the message on and says nothing when the agent takes it", async () => {
    const notices = { notify: vi.fn() };
    const call = vi.fn().mockResolvedValue(undefined);
    expect(await tellAgent(call, notices)).toBe(true);
    expect(call).toHaveBeenCalledOnce();
    expect(notices.notify).not.toHaveBeenCalled();
  });

  it("says why as a warning, in the daemon's words, when the agent can't take it", async () => {
    const notices = { notify: vi.fn() };
    const refused = new ApiError(409, "Claude Code isn't working on anything now. Send it as a new message.");
    expect(await tellAgent(() => Promise.reject(refused), notices)).toBe(false);
    expect(notices.notify).toHaveBeenCalledWith("Claude Code isn't working on anything now. Send it as a new message.", "warning");
  });
});

describe("putBack", () => {
  const shot = new File(["png"], "shot.png", { type: "image/png" });
  const log = new File(["log"], "log.txt", { type: "text/plain" });

  it("puts the text and files the agent couldn't take back in an empty box", () => {
    const box = { text: "", files: [] as File[] };
    putBack(box, "see this", [shot]);
    expect(box).toEqual({ text: "see this", files: [shot] });
  });

  it("keeps what was typed meanwhile, and the files attached since after the ones put back", () => {
    const box = { text: "something new", files: [log] };
    putBack(box, "see this", [shot]);
    expect(box).toEqual({ text: "something new", files: [shot, log] });
  });
});
