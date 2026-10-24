import { describe, expect, it } from "vitest";
import { comingText, endingText } from "./shutdown";

describe("endingText", () => {
  it("says when the daemon restarts or stops", () => {
    expect(endingText("restart", 0)).toBe("The assistant restarts now. This page reloads when it's back.");
    expect(endingText("restart", 1)).toContain("restarts once the run in progress ends.");
    expect(endingText("stop", 3)).toContain("stops once the 3 runs in progress end.");
    expect(endingText("stop", 0)).toContain("Start it again on the computer it runs on");
  });
});

describe("comingText", () => {
  it("tells every page a restart or stop is coming and what it waits for", () => {
    expect(comingText("lo9i", "restart", 0)).toBe("lo9i restarts now.");
    expect(comingText("lo9i", "restart", 2)).toBe("lo9i restarts once the 2 runs in progress end.");
    expect(comingText("lo9i", "stop", 1)).toBe("lo9i stops once the run in progress ends.");
  });
});
