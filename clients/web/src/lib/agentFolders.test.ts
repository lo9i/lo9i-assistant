import { describe, expect, it } from "vitest";
import { folderView } from "./agentFolders";

const folders = { workspace: "/Users/me/.lo9i/claude-workspace", recent: ["/Users/me/projects/lo9i"], home: "/Users/me" };

describe("the /claude folder picker", () => {
  it("offers the workspace and the folders used before, each picked at once", () => {
    const view = folderView(folders, null);
    expect(view.choices.map((c) => [c.label, c.action, c.path])).toEqual([
      ["Workspace", "pick", "/Users/me/.lo9i/claude-workspace"],
      ["/Users/me/projects/lo9i", "pick", "/Users/me/projects/lo9i"],
    ]);
    expect(view.primary).toMatchObject({ label: "Browse…", action: "browse", path: "/Users/me" });
  });

  it("browses into a folder, goes back up, and picks the one it's in", () => {
    const listing = { path: "/Users/me/projects", parent: "/Users/me", children: ["/Users/me/projects/new-app"] };
    const view = folderView(folders, listing);
    expect(view.description).toBe("/Users/me/projects");
    expect(view.choices).toEqual([
      { label: "Up", path: "/Users/me", action: "browse", up: true },
      { label: "new-app", path: "/Users/me/projects/new-app", action: "browse" },
    ]);
    expect(view.primary).toEqual({ label: "Use this folder", path: "/Users/me/projects", action: "pick" });
    expect(view.empty).toBe(false);
  });

  it("says when a folder has none inside, and offers no Up at the top", () => {
    const view = folderView(folders, { path: "/", parent: null, children: [] });
    expect(view.choices).toEqual([]);
    expect(view.empty).toBe(true);
  });

  it("offers nothing until the daemon has listed the folders", () => {
    expect(folderView(null, null)).toMatchObject({ choices: [], primary: null });
  });
});
