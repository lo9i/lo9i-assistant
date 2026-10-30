import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { RunStreams } from "./runStreams";
import type { Transport } from "./transport";
import type { RunEvent } from "./types";

function streams(): { runs: RunStreams; request: ReturnType<typeof vi.fn> } {
  const request = vi.fn().mockResolvedValue({ ok: true });
  const transport: Transport = { clientId: "tab", request, blob: vi.fn(), stream: vi.fn() };
  return { runs: new RunStreams(transport), request };
}

const text = (t: string): RunEvent => ({ type: "TextDelta", text: t }) as RunEvent;

/** The id the daemon was asked to follow the run under. */
function followId(request: ReturnType<typeof vi.fn>, call = 0): string {
  return decodeURIComponent((request.mock.calls[call][1] as string).split("/").pop()!);
}

async function collect(batches: AsyncIterable<RunEvent[]>): Promise<RunEvent[][]> {
  const got: RunEvent[][] = [];
  for await (const batch of batches) got.push(batch);
  return got;
}

describe("RunStreams", () => {
  it("asks for the run and gives its events in their batches until its end", async () => {
    const { runs, request } = streams();
    const following = collect(runs.follow("r1", new AbortController().signal));
    await vi.waitFor(() => expect(request).toHaveBeenCalled());
    expect(request.mock.calls[0][0]).toBe("PUT");
    expect(request.mock.calls[0][2]).toEqual({ run_id: "r1", after: 0 });
    const follow = followId(request);
    runs.receive("run_events", { follow, after: 0, events: [text("a"), text("b")] });
    runs.receive("run_events", { follow, after: 2, events: [text("c")] });
    runs.receive("run_end", { follow });
    expect(await following).toEqual([[text("a"), text("b")], [text("c")]]);
  });

  it("leaves other kinds of event to the page", () => {
    expect(streams().runs.receive("memory", {})).toBe(false);
  });

  it("asks again from where it got to when the stream opens again, and drops what comes twice", async () => {
    const { runs, request } = streams();
    const following = collect(runs.follow("r1", new AbortController().signal));
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    const follow = followId(request);
    runs.receive("run_events", { follow, after: 0, events: [text("a")] });
    runs.reopened();
    expect(request.mock.calls[1][2]).toEqual({ run_id: "r1", after: 1 });
    runs.receive("run_events", { follow, after: 0, events: [text("a"), text("b")] });
    runs.receive("run_end", { follow });
    expect(await following).toEqual([[text("a")], [text("b")]]);
  });

  it("fails when the daemon no longer knows the run", async () => {
    const { runs, request } = streams();
    const following = collect(runs.follow("r1", new AbortController().signal));
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    request.mockRejectedValueOnce(new ApiError(404, "Unknown or expired run"));
    runs.reopened();
    await expect(following).rejects.toBeInstanceOf(ApiError);
  });

  it("stops following when aborted, and tells the daemon", async () => {
    const { runs, request } = streams();
    const stop = new AbortController();
    const following = collect(runs.follow("r1", stop.signal));
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    stop.abort();
    await expect(following).rejects.toThrow();
    expect(request.mock.calls[1].slice(0, 2)).toEqual(["DELETE", `/events/runs/${followId(request)}`]);
  });
});
