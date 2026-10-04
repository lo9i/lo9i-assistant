import { describe, expect, it } from "vitest";
import { carriesFiles, droppedFiles } from "./dropped";

function item(file: File, folder = false): DataTransferItem {
  return {
    kind: "file",
    type: file.type,
    getAsFile: () => file,
    webkitGetAsEntry: () => ({ isDirectory: folder }) as FileSystemEntry,
    getAsString: () => {},
  } as unknown as DataTransferItem;
}

function transfer(types: string[], items: DataTransferItem[] = [], files: File[] = []): DataTransfer {
  return { types, items, files } as unknown as DataTransfer;
}

describe("dropped files", () => {
  it("offers to take a drag only when it carries files", () => {
    expect(carriesFiles(transfer(["Files"]))).toBe(true);
    expect(carriesFiles(transfer(["text/plain", "text/uri-list"]))).toBe(false);
    expect(carriesFiles(null)).toBe(false);
  });

  it("takes the files and leaves folders out, counting them", () => {
    const photo = new File(["x"], "photo.jpg", { type: "image/jpeg" });
    const folder = new File([], "Documents");
    const dropped = droppedFiles(transfer(["Files"], [item(photo), item(folder, true)]));
    expect(dropped.files.map((f) => f.name)).toEqual(["photo.jpg"]);
    expect(dropped.folders).toBe(1);
  });

  it("falls back to the file list when the browser gives no items", () => {
    const note = new File(["x"], "note.txt", { type: "text/plain" });
    expect(droppedFiles(transfer(["Files"], [], [note])).files).toEqual([note]);
  });
});
