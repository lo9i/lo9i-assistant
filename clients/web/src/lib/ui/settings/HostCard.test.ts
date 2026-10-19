import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import HostCard from "./HostCard.svelte";

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, hub: {}, notices: {} }),
  resource: () => ({
    data: {
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
    },
  }),
}));

describe("HostCard", () => {
  it("offers to restart and stop the assistant", () => {
    const { body } = render(HostCard);
    expect(body).toContain("board");
    expect(body).toContain("Restart");
    expect(body).toContain("Stop");
  });
});
