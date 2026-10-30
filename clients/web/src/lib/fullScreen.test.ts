import { describe, expect, it } from "vitest";
import { restoresOnEscape, toggled } from "./fullScreen";

const page = (dialog: boolean) => ({ querySelector: () => (dialog ? ({} as Element) : null) });

describe("full screen", () => {
  it("shows a card full screen, the page again when pressed again, or another card", () => {
    expect(toggled(null, "a")).toBe("a");
    expect(toggled("a", "a")).toBeNull();
    expect(toggled("a", "b")).toBe("b");
  });

  it("gives the page back on Esc", () => {
    expect(restoresOnEscape({ key: "Escape", defaultPrevented: false }, page(false))).toBe(true);
    expect(restoresOnEscape({ key: "Enter", defaultPrevented: false }, page(false))).toBe(false);
  });

  it("leaves Esc to a dialog open, and to what took it already", () => {
    expect(restoresOnEscape({ key: "Escape", defaultPrevented: false }, page(true))).toBe(false);
    expect(restoresOnEscape({ key: "Escape", defaultPrevented: true }, page(false))).toBe(false);
  });
});
