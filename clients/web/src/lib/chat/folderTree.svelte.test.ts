import { describe, expect, it } from "vitest";
import type { FolderContents } from "$lib/api/types";
import { FolderTree } from "./folderTree.svelte";

function folder(path: string, names: string[]): FolderContents {
  const entries = names.map((name) => {
    const isFolder = !name.includes(".");
    return { name, path: path ? `${path}/${name}` : name, folder: isFolder, size: 0, deleted: false };
  });
  return { path, entries, truncated: false };
}

/** A daemon listing `disk`, counting what it was asked for. */
function lister(disk: Record<string, string[]>) {
  const asked: string[] = [];
  const list = async (path: string) => {
    asked.push(path);
    if (!(path in disk)) throw new Error(`${path} isn't there.`);
    return folder(path, disk[path]);
  };
  return { asked, list };
}

describe("FolderTree", () => {
  it("lists a folder the first time it's opened, and not again when it's opened again", async () => {
    const daemon = lister({ "": ["src", "a.txt"], src: ["b.txt"] });
    const tree = new FolderTree(daemon.list);
    await tree.refresh();
    await tree.toggle("src");
    expect(tree.opened).toEqual({ src: true });
    await tree.toggle("src");
    await tree.toggle("src");
    expect(daemon.asked).toEqual(["", "src"]);
    const listing = tree.listings.src;
    expect("contents" in listing && listing.contents.entries.map((e) => e.path)).toEqual(["src/b.txt"]);
  });

  it("lists every open folder again on a refresh, closing one that went away", async () => {
    const disk: Record<string, string[]> = { "": ["src", "tmp"], src: ["b.txt"], tmp: [] };
    const daemon = lister(disk);
    const tree = new FolderTree(daemon.list);
    await tree.refresh();
    await tree.toggle("src");
    await tree.toggle("tmp");
    disk[""] = ["src"];
    disk.src = ["b.txt", "c.txt"];
    delete disk.tmp;
    await tree.refresh();
    expect(tree.opened).toEqual({ src: true });
    const listing = tree.listings.src;
    expect("contents" in listing && listing.contents.entries.map((e) => e.name)).toEqual(["b.txt", "c.txt"]);
  });

  it("keeps why a folder couldn't be listed", async () => {
    const tree = new FolderTree(lister({ "": ["gone"] }).list);
    await tree.refresh();
    await tree.toggle("gone");
    expect(tree.listings.gone).toEqual({ error: expect.stringContaining("gone isn't there.") });
  });

  it("reads every open folder at once on a refresh when it can, and says why for each when that fails", async () => {
    const daemon = lister({ "": ["src"], src: ["b.txt"] });
    const tree = new FolderTree(daemon.list);
    await tree.refresh();
    await tree.toggle("src");
    const together: string[][] = [];
    const readAll = async (paths: string[]) => {
      together.push(paths);
      return Object.fromEntries(paths.map((path) => [path, { contents: folder(path, path ? ["c.txt"] : ["src"]) }]));
    };
    await tree.refresh(readAll);
    expect([together, daemon.asked]).toEqual([[["", "src"]], ["", "src"]]);
    const listing = tree.listings.src;
    expect("contents" in listing && listing.contents.entries.map((e) => e.name)).toEqual(["c.txt"]);
    await tree.refresh(async () => {
      throw new Error("The folder is gone.");
    });
    expect(tree.listings.src).toEqual({ error: expect.stringContaining("The folder is gone.") });
  });
});
