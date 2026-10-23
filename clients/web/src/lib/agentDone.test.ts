import { describe, expect, it, vi } from "vitest";
import type { AgentFinished } from "./api/types";
import { announce } from "./agentDone";

const done: AgentFinished = { thread_id: "t1", agent: "Claude Code", ok: true, text: "Fixed 2 tests." };

function telling(visible: boolean, system = true) {
  return { chime: vi.fn(), visible: vi.fn(() => visible), system: vi.fn(() => system), toast: vi.fn() };
}

describe("announce", () => {
  it("plays the sound and shows its own notice while the page is in front", () => {
    const t = telling(true);
    const open = vi.fn();
    announce(done, { sound: true, popup: true }, t, open);
    expect(t.chime).toHaveBeenCalledOnce();
    expect(t.system).not.toHaveBeenCalled();
    expect(t.toast).toHaveBeenCalledWith("Claude Code finished: Fixed 2 tests.", "info", { label: "Open its conversation", run: open });
  });

  it("pops up a system notification while the page is behind, and its own when the browser won't", () => {
    const behind = telling(false);
    announce(done, { sound: false, popup: true }, behind, () => {});
    expect(behind.system).toHaveBeenCalledWith("Claude Code finished", "Fixed 2 tests.", expect.any(Function));
    expect(behind.toast).not.toHaveBeenCalled();
    expect(behind.chime).not.toHaveBeenCalled();
    const blocked = telling(false, false);
    announce({ ...done, ok: false, text: "No login" }, { sound: false, popup: true }, blocked, () => {});
    expect(blocked.toast).toHaveBeenCalledWith("Claude Code stopped with a problem: No login", "warning", expect.anything());
  });

  it("does nothing with both turned off", () => {
    const t = telling(false);
    announce(done, { sound: false, popup: false }, t, () => {});
    expect([t.chime, t.system, t.toast].every((f) => f.mock.calls.length === 0)).toBe(true);
  });
});
