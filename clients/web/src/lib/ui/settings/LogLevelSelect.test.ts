import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import LogLevelSelect from "./LogLevelSelect.svelte";

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, notices: {} }),
  resource: () => ({ data: { level: "DEBUG" } }),
}));

describe("LogLevelSelect", () => {
  it("offers every level and shows the one the daemon records at", () => {
    const { body } = render(LogLevelSelect, { props: { levels: ["DEBUG", "INFO", "WARNING", "ERROR"] } });
    expect(body).toContain("Record");
    for (const label of ["Debug and above", "Info and above", "Warning and above", "Error and above"]) {
      expect(body).toContain(label);
    }
    expect(body).toMatch(/<option value="DEBUG"[^>]*selected/);
    expect(body).not.toMatch(/<option value="INFO"[^>]*selected/);
  });
});
