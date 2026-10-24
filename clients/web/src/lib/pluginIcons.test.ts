import { describe, expect, it } from "vitest";
import daemon from "../../../../src/assistant/core/repositories/lucide_icons.json";
import { lucideIcon, lucideNames, svgUrl } from "./pluginIcons";

describe("plugins' icons", () => {
  it("names the same Lucide icons the daemon checks plugins against", () => {
    // After a Lucide update, write the new list to src/assistant/core/repositories/lucide_icons.json.
    expect(lucideNames()).toEqual(daemon);
  });

  it("loads a Lucide icon by name, and nothing for a name it doesn't have", async () => {
    expect(await lucideIcon("tv")).toBeTypeOf("function");
    expect(await lucideIcon("not-an-icon")).toBeNull();
  });

  it("gives an SVG as a data URL, whatever its characters", () => {
    const url = svgUrl('<svg xmlns="http://www.w3.org/2000/svg"><title>Café ✓</title></svg>');
    expect(url.startsWith("data:image/svg+xml;base64,")).toBe(true);
    const decoded = new TextDecoder().decode(Uint8Array.from(atob(url.split(",")[1]), (c) => c.charCodeAt(0)));
    expect(decoded).toContain("Café ✓");
  });
});
