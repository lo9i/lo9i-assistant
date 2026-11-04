import { describe, expect, it } from "vitest";
import type { OpenLoop } from "./api/types";
import { BILL_DUE, homeLoops } from "./homeLoops";

function loop(id: string, extra: Partial<OpenLoop> = {}): OpenLoop {
  return { id, text: id, source: "conversation", created_at: "2026-11-01T10:00", key: id, ...extra } as OpenLoop;
}

describe("Home's open loops", () => {
  it("lists the open ones but bills, those due first, the soonest first", () => {
    const loops = [
      loop("new"),
      loop("later", { due: "2026-11-20" }),
      loop("bill", { kind: BILL_DUE, due: "2026-11-05" }),
      loop("closed", { status: "done" }),
      loop("old"),
      loop("soon", { due: "2026-11-06" }),
      loop("dismissed", { status: "dismissed", due: "2026-11-01" }),
    ];
    expect(homeLoops(loops).map((l) => l.id)).toEqual(["soon", "later", "new", "old"]);
  });

  it("lists nothing when nothing is open", () => {
    expect(homeLoops([loop("a", { status: "done" })])).toEqual([]);
  });
});
