import { describe, expect, it } from "vitest";
import { answerable, coming, comingText, endingText, waitingText, type Coming } from "./shutdown";

const runs = (ending: "restart" | "stop", waiting: number, more: Partial<Coming> = {}): Coming => ({
  ending,
  waiting,
  update: false,
  canTakeBack: true,
  ...more,
});

describe("coming", () => {
  it("reads a pending ending or an event, and nothing once taken back", () => {
    expect(coming({ ending: "", waiting_for_runs: 0 })).toBeNull();
    expect(coming({ ending: "restart", waiting_for_runs: 1, taken_back: true })).toBeNull();
    expect(coming({ ending: "restart", waiting_for_runs: 1, waiting_for_update: true, can_take_back: false })).toEqual(
      runs("restart", 1, { update: true, canTakeBack: false }),
    );
  });
});

describe("endingText", () => {
  it("says when the daemon restarts or stops", () => {
    expect(endingText(runs("restart", 0))).toBe("The assistant restarts now. This page reloads when it's back.");
    expect(endingText(runs("restart", 1))).toContain("restarts once the run in progress ends.");
    expect(endingText(runs("stop", 3))).toContain("stops once the 3 runs in progress end.");
    expect(endingText(runs("stop", 0))).toContain("Start it again on the computer it runs on");
  });

  it("says it waits for an update being installed, not that it restarts now", () => {
    expect(endingText(runs("restart", 0, { update: true }))).toContain("restarts once the update being installed is done.");
    expect(endingText(runs("restart", 2, { update: true }))).toContain(
      "once the update being installed is done and the 2 runs in progress end.",
    );
  });
});

describe("comingText", () => {
  it("tells every page a restart or stop is coming and what it waits for", () => {
    expect(comingText("lo9i", runs("restart", 0))).toBe("lo9i restarts now.");
    expect(comingText("lo9i", runs("restart", 2))).toBe("lo9i restarts once the 2 runs in progress end.");
    expect(comingText("lo9i", runs("stop", 1))).toBe("lo9i stops once the run in progress ends.");
  });
});

describe("waitingText and answerable", () => {
  it("says what Cancel and Now do while it waits for runs", () => {
    expect(waitingText(runs("restart", 1))).toBe(
      "Cancel keeps the assistant running. Now cancels the runs in progress, and it restarts at once.",
    );
    expect(waitingText(runs("stop", 1))).toContain("and it stops at once.");
    expect(answerable(runs("restart", 1))).toEqual({ cancel: true, now: true });
  });

  it("offers no Cancel for the restart an installed update needs", () => {
    const update = runs("restart", 1, { canTakeBack: false });
    expect(waitingText(update)).toBe(
      "An update was installed, so it can't be cancelled: it restarts so the update runs. Now cancels the runs in progress, and it restarts at once.",
    );
    expect(answerable(update)).toEqual({ cancel: false, now: true });
  });

  it("offers Cancel but not Now while it waits only for an update being installed", () => {
    expect(answerable(runs("restart", 0, { update: true }))).toEqual({ cancel: true, now: false });
    expect(answerable(runs("restart", 0))).toEqual({ cancel: false, now: false });
  });
});
