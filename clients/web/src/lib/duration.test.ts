import { describe, expect, it } from "vitest";
import { duration } from "./duration";

const at = (minutes: number) => new Date(Date.UTC(2026, 8, 30) + minutes * 60000).toISOString();

describe("duration", () => {
  it("rounds down to minutes, hours or days", () => {
    expect(duration(at(0), at(0.5))).toBe("< 1 min");
    expect(duration(at(0), at(12))).toBe("12 min");
    expect(duration(at(0), at(125))).toBe("2 h 5 min");
    expect(duration(at(0), at(180))).toBe("3 h");
    expect(duration(at(0), at(60 * 24 + 5))).toBe("1 day");
    expect(duration(at(0), at(60 * 24 * 3))).toBe("3 days");
  });
});
