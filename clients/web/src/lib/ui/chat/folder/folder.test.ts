import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import { ChangeMarks } from "$lib/chat/folderChanges";
import ChangedFiles from "./ChangedFiles.svelte";
import FileText from "./FileText.svelte";
import FolderLevel from "./FolderLevel.svelte";

const nothing = () => {};

describe("FolderLevel", () => {
  const listings = {
    "": {
      contents: {
        path: "",
        truncated: false,
        entries: [
          { name: "src", path: "src", folder: true, size: 0, deleted: false },
          { name: "README.md", path: "README.md", folder: false, size: 10, deleted: false },
          { name: "old.py", path: "old.py", folder: false, size: 0, deleted: true },
        ],
      },
    },
    src: {
      contents: { path: "src", truncated: true, entries: [{ name: "app.py", path: "src/app.py", folder: false, size: 5, deleted: false }] },
    },
  };
  const marks = new ChangeMarks([
    { path: "src/app.py", status: "modified" },
    { path: "old.py", status: "deleted" },
  ]);

  it("shows the folder's entries, marking changes, and an open folder's inside it", () => {
    const props = { path: "", listings, opened: { src: true }, marks, picked: "src/app.py", ontoggle: nothing, onpick: nothing };
    const { body } = render(FolderLevel, { props });
    expect(body.indexOf(">src<")).toBeLessThan(body.indexOf(">app.py<"));
    expect(body.indexOf(">app.py<")).toBeLessThan(body.indexOf(">README.md<"));
    expect(body).toContain('title="Changes inside"');
    expect(body).toContain('title="Modified"');
    expect(body).toContain("More files than shown.");
    expect(body).toMatch(/class="row[^"]*picked[^"]*"[^>]*title="src\/app.py"/);
  });

  it("shows a file git says was deleted where it was, struck through and marked", () => {
    const props = { path: "", listings, opened: {}, marks, picked: null, ontoggle: nothing, onpick: nothing };
    const { body } = render(FolderLevel, { props });
    expect(body).toMatch(/class="row[^"]*gone[^"]*"[^>]*title="old.py"/);
    expect(body).toContain('title="Deleted"');
    expect(body).not.toMatch(/class="row[^"]*gone[^"]*"[^>]*title="README.md"/);
  });

  it("leaves a closed folder's inside out", () => {
    const props = { path: "", listings, opened: {}, marks, picked: null, ontoggle: nothing, onpick: nothing };
    expect(render(FolderLevel, { props }).body).not.toContain("app.py");
  });

  it("says why a folder couldn't be listed", () => {
    const props = {
      path: "",
      listings: { "": { error: "Can't read ." } },
      opened: {},
      marks,
      picked: null,
      ontoggle: nothing,
      onpick: nothing,
    };
    expect(render(FolderLevel, { props }).body).toContain("Can't read .");
  });
});

describe("ChangedFiles", () => {
  it("lists the changes, an untracked folder not to be opened but a deleted file to see what it had", () => {
    const changes = {
      repository: true,
      truncated: false,
      changes: [
        { path: "a.py", status: "modified" as const },
        { path: "old.py", status: "deleted" as const },
        { path: "docs/", status: "untracked" as const },
      ],
    };
    const { body } = render(ChangedFiles, { props: { changes, picked: null, onpick: nothing } });
    expect(body).toContain('<span class="pill">3</span>');
    expect(body).toMatch(/<button[^>]*title="a.py"(?![^>]*disabled)[^>]*>/);
    expect(body).toMatch(/<button[^>]*title="old.py"(?![^>]*disabled)[^>]*>/);
    expect(body).toMatch(/<button[^>]*title="docs\/"[^>]*disabled/);
  });

  it("says when the folder isn't a git repository", () => {
    const { body } = render(ChangedFiles, {
      props: { changes: { repository: false, changes: [], truncated: false }, picked: null, onpick: nothing },
    });
    expect(body).toContain("Not a git repository");
  });
});

describe("FileText", () => {
  const shown = { change: null, view: "text" as const, diff: null, error: "", onview: nothing, onback: nothing };

  it("shows a text file's text, saying when it's only its start", () => {
    const preview = { path: "a.py", size: 300 * 1024, text: "<b>x</b>", truncated: true };
    const { body } = render(FileText, { props: { ...shown, path: "a.py", preview, ondelete: nothing } });
    expect(body).toMatch(/<pre[^>]*>&lt;b>x&lt;\/b><\/pre>/);
    expect(body).toContain("Too big to show whole (300.0 KB)");
    expect(body).not.toContain("Whole file"); // a file git doesn't list as changed has nothing else to show
  });

  it("says a file that isn't text can't be previewed", () => {
    const preview = { path: "a.png", size: 10, text: null, truncated: false };
    const { body } = render(FileText, { props: { ...shown, path: "a.png", preview, ondelete: nothing } });
    expect(body).toContain("Can't be previewed");
    expect(body).not.toContain("<pre");
  });

  it("offers to move a file to the trash once it's read, not while it loads or can't be read", () => {
    const preview = { path: "a.py", size: 1, text: "x", truncated: false };
    const props = { ...shown, path: "a.py", ondelete: nothing };
    expect(render(FileText, { props: { ...props, preview } }).body).toContain('aria-label="Move this file to the trash"');
    expect(render(FileText, { props: { ...props, preview: null } }).body).not.toContain("to the trash");
    expect(render(FileText, { props: { ...props, preview: null, error: "Not Found" } }).body).not.toContain("to the trash");
  });

  it("doesn't offer to delete while deleting is off", () => {
    const preview = { path: "a.py", size: 1, text: "x", truncated: false };
    const { body } = render(FileText, { props: { ...shown, path: "a.py", preview } });
    expect(body).not.toContain("to the trash");
  });

  it("shows what changed in a changed file, its lines coloured, with its whole text a click away", () => {
    const diff = {
      path: "a.py",
      status: "modified" as const,
      text: "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
      truncated: false,
    };
    const props = { ...shown, path: "a.py", change: "modified" as const, view: "diff" as const, preview: null, diff, ondelete: nothing };
    const { body } = render(FileText, { props });
    expect(body).toContain('<span class="line line--removed svelte-');
    expect(body).toMatch(/line--added[^>]*>\+x = 2</);
    expect(body).toMatch(/line--hunk[^>]*>@@ -1 \+1 @@</);
    expect(body).toMatch(/line--meta[^>]*>--- a\/a.py</);
    expect(body).toMatch(/aria-pressed="true"[^>]*>Changes</);
    expect(body).toContain("Whole file");
    expect(body).toContain("Move this file to the trash");
  });

  it("shows a deleted file's changes only, and nothing to delete", () => {
    const diff = { path: "old.py", status: "deleted" as const, text: "@@ -1 +0,0 @@\n-gone\n", truncated: false };
    const props = { ...shown, path: "old.py", change: "deleted" as const, view: "diff" as const, preview: null, diff, ondelete: nothing };
    const { body } = render(FileText, { props });
    expect(body).toMatch(/line--removed[^>]*>-gone</);
    expect(body).not.toContain("Whole file");
    expect(body).not.toContain("to the trash");
  });
});

describe("ChangedFiles when they can't be read", () => {
  it("says why in place of Loading", () => {
    const { body } = render(ChangedFiles, { props: { changes: undefined, error: "Not Found", picked: null, onpick: nothing } });
    expect(body).toContain("Not Found");
    expect(body).not.toContain("Loading");
  });

  it("keeps the ones read before under why the last read failed", () => {
    const changes = { repository: true, truncated: false, changes: [{ path: "a.py", status: "modified" as const }] };
    const { body } = render(ChangedFiles, { props: { changes, error: "Not Found", picked: null, onpick: nothing } });
    expect(body.indexOf("Not Found")).toBeLessThan(body.indexOf('title="a.py"'));
  });
});
