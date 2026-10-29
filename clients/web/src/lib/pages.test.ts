import { describe, expect, it } from "vitest";
import { pageHref, pageLabel, pageUrl, themeMessage } from "./pages";

describe("pageUrl", () => {
  it("opens the page at a place on it, never outside it", () => {
    const local = { protocol: "http:", hostname: "127.0.0.1", port: "8765" };
    expect(pageUrl("watchlist", local, "dark", "titles/12")).toBe("http://127.0.0.1:8766/watchlist/titles/12?theme=dark");
    expect(pageUrl("watchlist", local, undefined, "titles/a b")).toBe("http://127.0.0.1:8766/watchlist/");
    expect(pageUrl("watchlist", local, undefined, "../hosts")).toBe("http://127.0.0.1:8766/watchlist/");
    expect(pageUrl("watchlist", local, undefined, "titles/../../x")).toBe("http://127.0.0.1:8766/watchlist/");
    expect(pageUrl("watchlist", local, undefined, "//evil.example")).toBe("http://127.0.0.1:8766/watchlist/");
    expect(pageHref("/app/pages/watchlist", "titles/12")).toBe("/app/pages/watchlist?path=titles%2F12");
    expect(pageHref("/app/pages/watchlist")).toBe("/app/pages/watchlist");
  });

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
