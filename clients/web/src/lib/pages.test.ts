import { describe, expect, it } from "vitest";
import { pageLabel, pageUrl } from "./pages";

describe("pageUrl", () => {
  it("is on the next port, local or over HTTPS", () => {
    expect(pageUrl("expenses", { protocol: "http:", hostname: "127.0.0.1", port: "8765" })).toBe("http://127.0.0.1:8766/expenses/");
    expect(pageUrl("expenses", { protocol: "https:", hostname: "board.ts.net", port: "" })).toBe("https://board.ts.net:444/expenses/");
  });
});

describe("pageLabel", () => {
  it("reads like a page name", () => {
    expect(pageLabel("expenses")).toBe("Expenses");
    expect(pageLabel("home_assistant")).toBe("Home assistant");
  });
});
