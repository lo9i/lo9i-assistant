import { describe, expect, it } from "vitest";
import type { UpdateStatus } from "./api/types";
import { canInstall, updateLine, versionText } from "./updates";

const base: UpdateStatus = {
  installed_from: "git",
  current: { sha: "a1b2c3d4e5f6", subject: "First", date: "2026-10-24T12:00:00Z" },
  upstream: "origin/main",
  behind: 0,
  new: [],
  checked_at: "",
  can_update: false,
  reason: "",
  state: "idle",
  step: "",
  error: "",
};

describe("updates", () => {
  it("names the version by its commit and day", () => {
    expect(versionText(base.current)).toMatch(/^a1b2c3d · /);
    expect(versionText(null)).toBe("Unknown");
  });

  it("says where the update stands", () => {
    expect(updateLine(base)).toBe("Not checked yet.");
    const checked = { ...base, checked_at: "2026-10-24T13:00:00Z", can_update: true };
    expect(updateLine(checked)).toBe("Up to date with origin/main.");
    expect(updateLine({ ...checked, behind: 2 })).toBe("2 new changes on origin/main.");
    expect(updateLine({ ...checked, state: "updating", step: "Building the web app" })).toBe("Building the web app…");
    expect(updateLine({ ...checked, state: "failed", error: "Building the web app failed: boom" })).toBe(
      "Building the web app failed: boom",
    );
    expect(updateLine({ ...base, checked_at: "x", reason: "This copy has changes that aren't committed." })).toBe(
      "This copy has changes that aren't committed.",
    );
  });

  it("offers Update only when there's something new it can install", () => {
    const ready = { ...base, checked_at: "x", can_update: true, behind: 1 };
    expect(canInstall(ready)).toBe(true);
    expect(canInstall({ ...ready, state: "failed" })).toBe(true);
    expect(canInstall({ ...ready, behind: 0 })).toBe(false);
    expect(canInstall({ ...ready, can_update: false })).toBe(false);
    expect(canInstall({ ...ready, state: "updating" })).toBe(false);
  });
});
