import { describe, expect, it, vi } from "vitest";
import type { ToolItem } from "./transcript";
import { WholeCalls } from "./wholeCalls.svelte";

const preview: ToolItem = {
  kind: "tool",
  id: 1,
  name: "bash",
  args: { detail: "seq 1 100" },
  output: "1\n2…",
  state: "done",
  callId: "c1",
  partial: true,
};
const whole = { name: "bash", args: { command: "seq 1 100" }, output: "1\n2\n3" };

describe("WholeCalls", () => {
  it("loads a partial call once, the first time it's opened", async () => {
    const calls = new WholeCalls();
    const load = vi.fn().mockResolvedValue(whole);
    const opened = calls.open(preview, load);
    expect(calls.get("c1")).toEqual({ state: "loading" });
    await opened;
    await calls.open(preview, load);
    expect(calls.get("c1")).toEqual({ state: "loaded", call: whole });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("leaves a call that's already whole alone", async () => {
    const calls = new WholeCalls();
    const load = vi.fn();
    await calls.open({ ...preview, partial: false }, load);
    await calls.open({ ...preview, callId: undefined }, load);
    expect(load).not.toHaveBeenCalled();
    expect(calls.get("c1")).toBeUndefined();
  });

  it("says it failed and tries again when opened again", async () => {
    const calls = new WholeCalls();
    const load = vi.fn().mockRejectedValueOnce(new Error("404")).mockResolvedValue(whole);
    await calls.open(preview, load);
    expect(calls.get("c1")).toEqual({ state: "failed" });
    await calls.open(preview, load);
    expect(calls.get("c1")).toEqual({ state: "loaded", call: whole });
  });

  it("loads a partial step inside a call by the call and its place, once, and leaves a whole one alone", async () => {
    const calls = new WholeCalls();
    const step = { name: "bash", args: { command: "cat log" }, output: "line…", state: "done" as const, partial: true };
    const load = vi.fn().mockResolvedValue(whole);
    const call = { ...preview, partial: false, steps: [step, { ...step, partial: false }] };
    await calls.openStep(call, 0, step, load);
    await calls.openStep(call, 0, step, load);
    await calls.openStep(call, 1, { ...step, partial: false }, load);
    expect(load).toHaveBeenCalledTimes(1);
    expect(load).toHaveBeenCalledWith("c1", 0);
    expect(calls.getStep("c1", 0)).toEqual({ state: "loaded", call: whole });
    expect(calls.getStep("c1", 1)).toBeUndefined();
    expect(calls.get("c1")).toBeUndefined();
  });
});
