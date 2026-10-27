import { describe, expect, it } from "vitest";
import { answerable, withoutMarkers } from "./choices";

describe("answerable", () => {
  it("takes the choices out of the marker at the end", () => {
    expect(answerable("Should I commit and push?\n\n<!-- choices: Push | Commit only | Cancel -->\n")).toEqual({
      text: "Should I commit and push?",
      choices: ["Push", "Commit only", "Cancel"],
    });
  });

  it("has no choices without a marker at the end", () => {
    expect(answerable("Done.").choices).toEqual([]);
    expect(answerable("<!-- choices: Yes | No --> Done.")).toEqual({ text: " Done.", choices: [] });
  });

  it("leaves out empty choices", () => {
    expect(answerable("Go?<!-- choices: Yes || No | -->").choices).toEqual(["Yes", "No"]);
  });
});

describe("withoutMarkers", () => {
  it("holds back a marker still streaming", () => {
    expect(withoutMarkers("Push it?\n\n<!-- choices: Ye")).toBe("Push it?");
    expect(withoutMarkers("Push it?\n\n<!-")).toBe("Push it?");
  });

  it("keeps other comments and text", () => {
    expect(withoutMarkers("1 < 2 <!-- note -->")).toBe("1 < 2 <!-- note -->");
  });
});
