import { describe, expect, it } from "vitest";
import { callTime } from "./callTime";

describe("callTime", () => {
  const now = new Date(2026, 10, 4, 15, 0);

  it("shows the time a call started today, and its day too when it started another day", () => {
    const today = callTime(new Date(2026, 10, 4, 9, 5).toISOString(), now);
    expect(today?.shown).toMatch(/09:05/);
    expect(today?.whole).toMatch(/2026/);
    expect(callTime(new Date(2026, 10, 2, 9, 5).toISOString(), now)?.shown).toMatch(/2.*09:05|09:05.*2/);
  });

  it("shows nothing for a call from before its time was kept", () => {
    expect(callTime(undefined, now)).toBeNull();
    expect(callTime("", now)).toBeNull();
  });
});
