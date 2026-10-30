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
          { name: "src", path: "src", folder: true, size: 0 },
          { name: "README.md", path: "README.md", folder: false, size: 10 },
        ],
      },
    },
    src: { contents: { path: "src", truncated: true, entries: [{ name: "app.py", path: "src/app.py", folder: false, size: 5 }] } },
  };
  const marks = new ChangeMarks([{ path: "src/app.py", status: "modified" }]);

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
  it("lists the changes, a deleted file and an untracked folder not to be opened", () => {
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
    expect(body).toMatch(/<button[^>]*title="old.py"[^>]*disabled/);
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
  it("shows a text file's text, saying when it's only its start", () => {
    const preview = { path: "a.py", size: 300 * 1024, text: "<b>x</b>", truncated: true };
    const { body } = render(FileText, { props: { path: "a.py", preview, error: "", onback: nothing, ondelete: nothing } });
    expect(body).toMatch(/<pre[^>]*>&lt;b>x&lt;\/b><\/pre>/);
    expect(body).toContain("Too big to show whole (300.0 KB)");
  });

  it("says a file that isn't text can't be previewed", () => {
    const preview = { path: "a.png", size: 10, text: null, truncated: false };
    const { body } = render(FileText, { props: { path: "a.png", preview, error: "", onback: nothing, ondelete: nothing } });
    expect(body).toContain("Can't be previewed");
    expect(body).not.toContain("<pre");
  });

  it("offers to delete a file once it's read, not while it loads or can't be read", () => {
    const preview = { path: "a.py", size: 1, text: "x", truncated: false };
    const props = { path: "a.py", error: "", onback: nothing, ondelete: nothing };
    expect(render(FileText, { props: { ...props, preview } }).body).toContain('aria-label="Delete this file"');
    expect(render(FileText, { props: { ...props, preview: null } }).body).not.toContain("Delete this file");
    expect(render(FileText, { props: { ...props, preview: null, error: "Not Found" } }).body).not.toContain("Delete this file");
  });

  it("doesn't offer to delete while deleting is off", () => {
    const preview = { path: "a.py", size: 1, text: "x", truncated: false };
    const { body } = render(FileText, { props: { path: "a.py", preview, error: "", onback: nothing } });
    expect(body).not.toContain("Delete this file");
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
