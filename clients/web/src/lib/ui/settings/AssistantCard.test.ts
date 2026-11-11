import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import AssistantCard from "./AssistantCard.svelte";

const loaded = vi.hoisted(() => ({ host: {} as Record<string, string> }));
// Each resource is what its loader asks the client for.
vi.mock("$lib/daemon.svelte", async () => {
  const { fakeSystem } = await import("./system.fixtures");
  return {
    useDaemon: () => ({ client: {}, hub: { on: () => () => {} }, notices: {} }),
    resource: (load: (client: unknown) => unknown) => ({ data: load(fakeSystem(loaded.host)), reload: () => {} }),
  };
});

describe("AssistantCard", () => {
  it("offers to restart and stop the assistant", () => {
    const { body } = render(AssistantCard);
    expect(body).toContain("Restart");
    expect(body).toContain("Stop");
  });

  it("shows what's new upstream, and offers to check and to update", () => {
    const { body } = render(AssistantCard);
    expect(body).toContain("1 new change on origin/main.");
    expect(body).toContain("subagent");
    expect(body).toContain("Check for updates");
    expect(body).toContain("Update and restart");
  });

  it("says before it's pressed that stopping asks for the administrator password", () => {
    loaded.host = { stop_note: "Start at boot is on: stopping asks for the administrator password on this Mac." };
    const { body } = render(AssistantCard);
    loaded.host = {};
    expect(body).toContain("stopping asks for the administrator password on this Mac.");
  });
});
