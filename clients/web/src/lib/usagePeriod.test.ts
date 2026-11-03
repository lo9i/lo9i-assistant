import { describe, expect, it } from "vitest";
import { usageRange } from "./usagePeriod";

describe("usageRange", () => {
  it("starts today at local midnight", () => {
    const { days, since } = usageRange("today", new Date(2026, 10, 3, 21, 45, 12));
    expect(days).toBe(1);
    expect(since).toEqual(new Date(2026, 10, 3, 0, 0, 0, 0));
  });

  it("asks for the last days without a start", () => {
    expect(usageRange(30)).toEqual({ days: 30 });
  });
});
