import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import AboutYouDialog from "./AboutYouDialog.svelte";

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: { memory: { aboutYou: () => new Promise(() => {}) } } }),
}));

describe("AboutYouDialog", () => {
  it("asks for the name, how to reply and what to help with", () => {
    const { body } = render(AboutYouDialog, { props: { onclose: () => {} } });
    expect(body).toContain("About you");
    expect(body).toContain("What should it call you?");
    expect(body).toContain("Short and to the point");
    expect(body).toContain("Movies and YouTube");
    expect(body).toContain("Servers and hosts");
    expect(body).toContain("Later");
  });
});
