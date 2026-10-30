// What git says changed in the folder a conversation is handed to (src/assistant/core/handed_folder/changes.py), as
// the side panel marks it in the tree: a file by its change, a folder with changes inside by a dot.
import type { FileChange } from "$lib/api/types";

export type ChangeKind = FileChange["status"];
/** A file's change, or `inside` for a folder with changes in it. */
export type Mark = ChangeKind | "inside";

export class ChangeMarks {
  private readonly files = new Map<string, ChangeKind>();
  // Git lists a folder nothing in is tracked once, as "docs/", for everything inside it.
  private readonly untracked: string[] = [];
  private readonly holding = new Set<string>();

  constructor(changes: FileChange[]) {
    for (const change of changes) {
      if (change.path.endsWith("/")) this.untracked.push(change.path);
      else this.files.set(change.path, change.status);
      parents(change.path).forEach((folder) => this.holding.add(folder));
    }
  }

  /** How the tree marks the file or folder at `path`; null when nothing changed there. */
  of(path: string, folder: boolean): Mark | null {
    if (this.untracked.some((prefix) => `${path}/`.startsWith(prefix))) return "untracked";
    if (folder) return this.holding.has(path) ? "inside" : null;
    return this.files.get(path) ?? null;
  }
}

/** The folders `path` is in, outermost first: "a/b/c.txt" is in "a" and "a/b". */
function parents(path: string): string[] {
  const parts = path.replace(/\/$/, "").split("/").slice(0, -1);
  return parts.map((_, i) => parts.slice(0, i + 1).join("/"));
}

/** The letter a change shows as, as git's short status: M, A, D, or U for untracked. */
export function changeLetter(kind: ChangeKind): string {
  return { modified: "M", added: "A", deleted: "D", untracked: "U" }[kind];
}
