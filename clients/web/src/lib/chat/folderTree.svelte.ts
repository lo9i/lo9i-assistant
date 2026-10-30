// The tree of the folder a conversation is handed to, as the side panel shows it: each folder listed by the daemon
// when it's first opened (src/assistant/core/handed_folder/contents.py), and listed again, with every open one, on
// a refresh, so files the agent added or removed show: all of them in one request where the daemon reads them
// together (the handed folder's, which asks git once), else one at a time.
import type { FolderContents } from "$lib/api/types";
import { describe } from "$lib/notices";

/** A folder's listing, or why it couldn't be read. */
export type Listing = { contents: FolderContents } | { error: string };

/** Reads every folder in `paths` at once, by path. */
export type ReadAll = (paths: string[]) => Promise<Record<string, Listing>>;

export class FolderTree {
  // By path, "" for the folder itself.
  listings = $state<Record<string, Listing>>({});
  opened = $state<Record<string, boolean>>({});

  constructor(private readonly list: (path: string) => Promise<FolderContents>) {}

  /** Opens a closed folder, listing it the first time; closes an open one. */
  async toggle(path: string): Promise<void> {
    if (this.opened[path]) {
      delete this.opened[path];
      return;
    }
    this.opened[path] = true;
    if (!this.listings[path]) await this.load(path);
  }

  /** The folder and every open folder listed again, by `readAll` when given; a folder gone since is closed. */
  async refresh(readAll?: ReadAll): Promise<void> {
    const paths = ["", ...Object.keys(this.opened)];
    await (readAll ? this.loadAll(paths, readAll) : Promise.all(paths.map((path) => this.load(path))));
    for (const path of Object.keys(this.opened)) if (!this.shown(path)) delete this.opened[path];
  }

  private async loadAll(paths: string[], readAll: ReadAll): Promise<void> {
    try {
      Object.assign(this.listings, await readAll(paths));
    } catch (e) {
      const error = describe(e);
      for (const path of paths) this.listings[path] = { error };
    }
  }

  private async load(path: string): Promise<void> {
    try {
      this.listings[path] = { contents: await this.list(path) };
    } catch (e) {
      this.listings[path] = { error: describe(e) };
    }
  }

  /** Whether `path` is still listed in its parent's listing. */
  private shown(path: string): boolean {
    const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
    const listing = this.listings[parent];
    return !!listing && "contents" in listing && listing.contents.entries.some((e) => e.path === path);
  }
}
