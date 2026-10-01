import { describe, expect, it } from "vitest";
import { pastedFiles } from "./pasted";

function clipboard(...files: File[]): DataTransfer {
  return { files } as unknown as DataTransfer;
}

describe("pastedFiles", () => {
  it("names a pasted screenshot by the time, like the terminal app", () => {
    const screenshot = new File(["png"], "image.png", { type: "image/png" });
    const [file] = pastedFiles(clipboard(screenshot), new Date(2026, 8, 30, 9, 5, 7));
    expect(file.name).toBe("pasted-090507.png");
    expect(file.type).toBe("image/png");
  });

  it("keeps a copied file's name, and finds nothing in a text paste", () => {
    const notes = new File(["hi"], "notes.txt", { type: "text/plain" });
    expect(pastedFiles(clipboard(notes)).map((f) => f.name)).toEqual(["notes.txt"]);
    expect(pastedFiles(clipboard())).toEqual([]);
  });
});
