import { describe, expect, it } from "vitest";
import type { HomeSection } from "./api/types";
import { dayOf, itemWhen, moved, updatedLabel, withSection, withoutSection } from "./home";

const section = (id: string, title = id): HomeSection => ({ id, title, prompt: `${title} today.`, plugins: [] });

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
