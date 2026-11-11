import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import HostCard from "./HostCard.svelte";
import { host, update } from "./system.fixtures";

// Each resource is what its loader asks the client for.
vi.mock("$lib/daemon.svelte", async () => {
  const { fakeSystem } = await import("./system.fixtures");
  return {
    useDaemon: () => ({ client: {}, hub: { on: () => () => {} }, notices: {} }),
    resource: (load: (client: unknown) => unknown) => ({ data: load(fakeSystem()) }),
  };
});

describe("HostCard", () => {
  it("says what the computer is and how it's doing", () => {
    const { body } = render(HostCard);
    expect(body).toContain(host.hostname);
    expect(body).toContain(host.os);
    expect(body).toContain("CPython 3.12.9");
  });

  it("shows the version lo9i runs with its commit, and leaves updating to the Assistant card", () => {
    const { body } = render(HostCard);
    expect(body).toContain("v0.1.0 · a1b2c3d");
    expect(body).not.toContain(update.new[0].subject);
    expect(body).not.toContain("Restart");
  });
});
