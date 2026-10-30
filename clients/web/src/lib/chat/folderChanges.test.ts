import { describe, expect, it } from "vitest";
import { ChangeMarks, changeLetter, diffLines } from "./folderChanges";

describe("ChangeMarks", () => {
  const marks = new ChangeMarks([
    { path: "src/app.py", status: "modified" },
    { path: "src/lib/new.ts", status: "added" },
    { path: "old.txt", status: "deleted" },
    { path: "docs/", status: "untracked" },
  ]);

  it("marks a changed file with its change", () => {
    expect(marks.of("src/app.py", false)).toBe("modified");
    expect(marks.of("src/lib/new.ts", false)).toBe("added");
    expect(marks.of("README.md", false)).toBeNull();
  });

  it("marks the folders a change is in, at every level", () => {
    expect(marks.of("src", true)).toBe("inside");
    expect(marks.of("src/lib", true)).toBe("inside");
    expect(marks.of("srcs", true)).toBeNull();
  });

  it("marks an untracked folder and everything in it as untracked", () => {
    expect(marks.of("docs", true)).toBe("untracked");
    expect(marks.of("docs/guide/a.md", false)).toBe("untracked");
    expect(marks.of("docsy.md", false)).toBeNull();
  });

  it("writes changes as git's short status", () => {
    expect(["modified", "added", "deleted", "untracked"].map((k) => changeLetter(k as never))).toEqual(["M", "A", "D", "U"]);
  });
});

describe("diffLines", () => {
  it("reads git's lines about the file, then each hunk's added, removed and unchanged lines", () => {
    const text = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n keep\n-old\n+new\n\\ No newline at end of file\n";
    expect(diffLines(text).map((l) => l.kind)).toEqual(["meta", "meta", "meta", "hunk", "context", "removed", "added", "meta"]);
  });
});
