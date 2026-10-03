import { describe, expect, it } from "vitest";
import { known, offered, parse } from "./commands";

describe("commands", () => {
  it("offers commands while the name is typed", () => {
    expect(offered("/").length).toBeGreaterThan(10);
    expect(offered("/s").map((c) => c.name)).toEqual(["/sessions", "/settings", "/skills", "/slack", "/startup"]);
    expect(offered("/name Max")).toEqual([]);
    expect(offered("hello")).toEqual([]);
  });

  it("splits a command line", () => {
    expect(parse("/name  Max Power ")).toEqual({ name: "/name", arg: "Max Power" });
    expect(parse("/new")).toEqual({ name: "/new", arg: "" });
    expect(parse("hello /new")).toBeNull();
    expect(known("/jobs") && !known("/mouse")).toBe(true);
  });
});
