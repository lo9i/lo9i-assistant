import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { tellAgent } from "./agentWork";

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
