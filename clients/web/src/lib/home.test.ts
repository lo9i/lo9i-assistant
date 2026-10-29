import { describe, expect, it } from "vitest";
import type { HomeSection } from "./api/types";
import {
  BUSY_ITEMS,
  cardColumns,
  dayOf,
  isWide,
  itemWhen,
  linked,
  moved,
  snappedColumns,
  updatedLabel,
  whileVisible,
  withColumns,
  withSection,
  withoutSection,
} from "./home";

const section = (id: string, title = id): HomeSection => ({ id, title, prompt: `${title} today.`, plugins: [], columns: 0 });

describe("an item's link", () => {
  it("is its url, and its subtitle is left as it is", () => {
    expect(linked({ subtitle: "366 points · 110 comments", url: "https://example.com/cnc" })).toEqual({
      subtitle: "366 points · 110 comments",
      url: "https://example.com/cnc",
    });
  });

  it("is taken out of the subtitle when it was written there, with its separator", () => {
    const item = { subtitle: "629 points · 139 comments · https://news.ycombinator.com/item?id=1", url: "" };
    expect(linked(item)).toEqual({ subtitle: "629 points · 139 comments", url: "https://news.ycombinator.com/item?id=1" });
    expect(linked({ subtitle: "https://a.example/x", url: "" })).toEqual({ subtitle: "", url: "https://a.example/x" });
  });

  it("is none for an item without an address", () => {
    expect(linked({ subtitle: "T2 E7, Ace of Spades", url: "" })).toEqual({ subtitle: "T2 E7, Ace of Spades", url: "" });
  });
});

describe("a card's width", () => {
  const busy = Array(BUSY_ITEMS + 1).fill({});

  it("is two columns only for a busy card", () => {
    expect(isWide(Array(BUSY_ITEMS).fill({}))).toBe(false);
    expect(isWide(busy)).toBe(true);
    expect(cardColumns({ columns: 0 }, [])).toBe(1);
    expect(cardColumns({ columns: 0 }, busy)).toBe(2);
  });

  it("is the one the user gave it, busy or not", () => {
    expect(cardColumns({ columns: 3 }, [])).toBe(3);
    expect(cardColumns({ columns: 1 }, busy)).toBe(1);
  });

  it("snaps to the nearest column the page has while it's dragged", () => {
    expect(snappedColumns(320, 320, 16, 4)).toBe(1);
    expect(snappedColumns(560, 320, 16, 4)).toBe(2);
    expect(snappedColumns(1000, 320, 16, 4)).toBe(3);
    expect(snappedColumns(1000, 320, 16, 2)).toBe(2);
    expect(snappedColumns(40, 320, 16, 4)).toBe(1);
  });

  it("is saved with its section", () => {
    expect(withColumns([section("a"), section("b")], "b", 2).map((s) => s.columns)).toEqual([0, 2]);
  });
});

describe("when an item is", () => {
  const today = "2026-10-22";

  it("shows only the time for today", () => {
    expect(itemWhen({ date: today, time: "09:00" }, today)).toBe("09:00");
    expect(itemWhen({ date: "", time: "21:30" }, today)).toBe("21:30");
    expect(itemWhen({ date: today, time: "" }, today)).toBe("Today");
  });

  it("names the days next to today and dates the others", () => {
    expect(itemWhen({ date: "2026-10-23", time: "21:00" }, today)).toBe("Tomorrow 21:00");
    expect(itemWhen({ date: "2026-10-21", time: "" }, today)).toBe("Yesterday");
    expect(itemWhen({ date: "2026-10-30", time: "" }, today)).toBe("Fri 30 Oct");
    expect(itemWhen({ date: "2026-10-01", time: "" }, today)).toBe("Thu 01 Oct");
  });

  it("is empty for an item without a day or a time", () => {
    expect(itemWhen({ date: "", time: "" }, today)).toBe("");
  });

  it("finds today in the browser's time zone", () => {
    expect(dayOf(new Date("2026-10-22T02:00:00Z"), "America/Argentina/Buenos_Aires")).toBe("2026-10-21");
    expect(dayOf(new Date("2026-10-22T02:00:00Z"), "UTC")).toBe("2026-10-22");
  });
});

describe("when Home was updated", () => {
  const now = new Date("2026-10-22T15:00:00Z");

  it("shows the time today and the day before", () => {
    expect(updatedLabel("2026-10-22T10:32:00+00:00", now, "UTC")).toBe("Updated 10:32");
    expect(updatedLabel("2026-10-21T18:05:00+00:00", now, "UTC")).toBe("Updated Wed 21 Oct 18:05");
  });

  it("is empty before the first refresh", () => {
    expect(updatedLabel("", now, "UTC")).toBe("");
  });
});

describe("editing the sections", () => {
  const sections = [section("a"), section("b"), section("c")];

  it("replaces an edited section and adds a new one at the end", () => {
    expect(withSection(sections, section("b", "Bills")).map((s) => s.title)).toEqual(["a", "Bills", "c"]);
    expect(withSection(sections, { ...section("", "New") }).map((s) => s.title)).toEqual(["a", "b", "c", "New"]);
  });

  it("removes one", () => {
    expect(withoutSection(sections, "b").map((s) => s.id)).toEqual(["a", "c"]);
  });

  it("moves one up or down, and leaves the ends alone", () => {
    expect(moved(sections, "b", -1).map((s) => s.id)).toEqual(["b", "a", "c"]);
    expect(moved(sections, "b", 1).map((s) => s.id)).toEqual(["a", "c", "b"]);
    expect(moved(sections, "a", -1)).toBe(sections);
    expect(moved(sections, "c", 1)).toBe(sections);
  });
});

describe("following whether the page is visible", () => {
  class Page extends EventTarget {
    visibilityState: DocumentVisibilityState = "visible";
    show(state: DocumentVisibilityState): void {
      this.visibilityState = state;
      this.dispatchEvent(new Event("visibilitychange"));
    }
  }

  it("says when it shows and hides, and hides when stopped", () => {
    const page = new Page();
    const said: string[] = [];
    const stop = whileVisible(
      page,
      () => said.push("shown"),
      () => said.push("hidden"),
    );
    page.show("hidden");
    page.show("hidden");
    page.show("visible");
    stop();
    page.show("hidden");
    expect(said).toEqual(["shown", "hidden", "shown", "hidden"]);
  });

  it("waits for a page that starts hidden", () => {
    const page = new Page();
    page.visibilityState = "hidden";
    const said: string[] = [];
    const stop = whileVisible(
      page,
      () => said.push("shown"),
      () => said.push("hidden"),
    );
    stop();
    expect(said).toEqual([]);
  });
});
