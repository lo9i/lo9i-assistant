import { describe as group, expect, it } from "vitest";
import { describeKept, keptKeys, keptName } from "./keptKeys.svelte";

group("keptKeys", () => {
  it("names the keys and the repository token", () => {
    expect(describeKept({ plugin: "x", keys: ["A", "B"], repository: "u", repository_name: "me/p" })).toBe("A, B and the token for me/p");
    expect(describeKept({ plugin: "x", keys: ["A"], repository: "", repository_name: "" })).toBe("A");
  });

  it("lists a plugin's keys by the plugin, and a token left on its own by its repository", () => {
    expect(keptName({ plugin: "hello", keys: ["A"], repository: "", repository_name: "" })).toBe("hello");
    expect(keptName({ plugin: "", keys: [], repository: "u", repository_name: "me/p" })).toBe("Token for me/p");
  });

  it("asks only when something was kept", () => {
    keptKeys.ask(null);
    expect(keptKeys.pending).toBeNull();
    keptKeys.ask({ plugin: "x", keys: ["A"], repository: "", repository_name: "" });
    expect(keptKeys.pending?.plugin).toBe("x");
  });
});
