import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import HostCard from "./HostCard.svelte";

const host = {
  os: "Linux 7.0.0",
  arch: "x86_64",
  hostname: "board",
  python: "CPython 3.12.9",
  version: "0.1.0",
  cpu_cores: 4,
  cpu_percent: 5,
  memory_used: 1,
  memory_total: 2,
  disk_used: 1,
  disk_total: 2,
  uptime_seconds: 60,
  load_average: [],
};

const update = {
  installed_from: "git",
  current: { sha: "a1b2c3d4e5", subject: "First", date: "2026-10-24T12:00:00Z" },
  upstream: "origin/main",
  behind: 1,
  new: [{ sha: "b2c3d4e5f6", subject: "Show the subagent's steps", date: "2026-10-24T13:00:00Z" }],
  checked_at: "2026-10-24T14:00:00Z",
  can_update: true,
  reason: "",
  state: "idle",
  step: "",
  error: "",
};

// The card reads the host first, then the update's status.
const loaded = vi.hoisted(() => ({ calls: 0 }));
vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, hub: { on: () => () => {} }, notices: {} }),
  resource: () => ({ data: loaded.calls++ % 2 === 0 ? host : update }),
}));

describe("HostCard", () => {
  it("offers to restart and stop the assistant", () => {
    const { body } = render(HostCard);
    expect(body).toContain("board");
    expect(body).toContain("Restart");
    expect(body).toContain("Stop");
  });

  it("shows the commit it runs, what's new, and offers to update", () => {
    const { body } = render(HostCard);
    expect(body).toContain("v0.1.0 · a1b2c3d");
    expect(body).toContain("1 new change on origin/main.");
    expect(body).toContain("subagent");
    expect(body).toContain("Check for updates");
    expect(body).toContain("Update and restart");
  });
});
