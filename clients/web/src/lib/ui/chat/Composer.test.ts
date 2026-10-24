import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ notices: { notify: vi.fn(), report: vi.fn() } }) }));

const { default: Composer } = await import("./Composer.svelte");

const steering = { agent: "Claude Code", onsteer: () => {} };
const shot = new File(["png"], "shot.png", { type: "image/png" });

function composer(text: string, files: File[]): string {
  const props = { busy: true, running: true, onsend: () => {}, onstop: () => {}, oncommand: () => {}, text, files, steering };
  return render(Composer, { props }).body;
}

describe("Composer while the agent works", () => {
  it("offers to send files alone to the agent", () => {
    expect(composer("", [shot])).toContain('aria-label="Send to Claude Code"');
  });

  it("offers nothing to send with neither text nor files", () => {
    expect(composer("", [])).not.toContain('aria-label="Send to Claude Code"');
  });
});
