import { describe, expect, it } from "vitest";
import { pageLabel, pageUrl, themeMessage } from "./pages";

describe("pageUrl", () => {
  it("is on the next port, local or over HTTPS", () => {
    expect(pageUrl("expenses", { protocol: "http:", hostname: "127.0.0.1", port: "8765" })).toBe("http://127.0.0.1:8766/expenses/");
    expect(pageUrl("expenses", { protocol: "https:", hostname: "board.ts.net", port: "" })).toBe("https://board.ts.net:444/expenses/");
  });

  it("tells the page the app's theme in its address, and in a message when it changes", () => {
    const local = { protocol: "http:", hostname: "127.0.0.1", port: "8765" };
    expect(pageUrl("hosts", local, "light")).toBe("http://127.0.0.1:8766/hosts/?theme=light");
    expect(themeMessage("dark")).toEqual({ type: "lo9i:theme", theme: "dark" });
  });
});

describe("pageLabel", () => {
  it("reads like a page name", () => {
    expect(pageLabel("expenses")).toBe("Expenses");
    expect(pageLabel("home_assistant")).toBe("Home assistant");
  });
});
