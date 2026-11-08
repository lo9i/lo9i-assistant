import { describe, expect, it } from "vitest";
import daemon from "../../../../src/lo9i/core/repositories/lucide_icons.json";
import { genericIcon, iconColor, lucideIcon, lucideNames, svgUrl } from "./pluginIcons";

describe("plugins' icons", () => {
  it("names the same Lucide icons the daemon checks plugins against", () => {
    // After a Lucide update, write the new list to src/lo9i/core/repositories/lucide_icons.json.
    expect(lucideNames()).toEqual(daemon);
  });

  it("loads a Lucide icon by name, and nothing for a name it doesn't have", async () => {
    expect(await lucideIcon("tv")).toBeTypeOf("function");
    expect(await lucideIcon("not-an-icon")).toBeNull();
  });

  it("gives the generic icon by its name too, as it's the one Lucide icon the app holds already", async () => {
    expect(await lucideIcon("panels-top-left")).toBe(genericIcon);
  });

  it("gives an SVG as a data URL, whatever its characters", () => {
    const url = svgUrl('<svg xmlns="http://www.w3.org/2000/svg"><title>Café ✓</title></svg>');
    expect(url.startsWith("data:image/svg+xml;base64,")).toBe(true);
    const decoded = new TextDecoder().decode(Uint8Array.from(atob(url.split(",")[1]), (c) => c.charCodeAt(0)));
    expect(decoded).toContain("Café ✓");
  });

  it("reads the colour an SVG icon draws in most, leaving out black, white and icons in the text colour", () => {
    const svg =
      '<svg><path fill="#D97757" d="M0"/><path fill="#fff" d="M1"/><path style="fill: #d97757" d="M2"/><path stroke="#123456"/></svg>';
    expect(iconColor({ name: "", svg, mono: false })).toBe("#d97757");
    expect(iconColor({ name: "", svg, mono: true })).toBeNull();
    expect(iconColor({ name: "bot", svg: "", mono: false })).toBeNull();
    expect(iconColor(null)).toBeNull();
  });
});
