import { describe, expect, it } from "vitest";
import { endingText } from "./shutdown";

describe("endingText", () => {
  it("says when the daemon restarts or stops", () => {
    expect(endingText("restart", 0)).toBe("The assistant restarts now. This page reloads when it's back.");
    expect(endingText("restart", 1)).toContain("restarts once the run in progress ends.");
    expect(endingText("stop", 3)).toContain("stops once the 3 runs in progress end.");
    expect(endingText("stop", 0)).toContain("Start it again on the computer it runs on");
  });
});
