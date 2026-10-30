// The tree of the folder a conversation is handed to, as the side panel shows it: each folder listed by the daemon
// when it's first opened (src/assistant/core/handed_folder/contents.py), and listed again, with every open one, on
// a refresh, so files the agent added or removed show.
import type { FolderContents } from "$lib/api/types";
import { describe } from "$lib/notices";

/** A folder's listing, or why it couldn't be read. */
export type Listing = { contents: FolderContents } | { error: string };

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

  /** The folder and every open folder listed again; a folder gone since is closed. */
  async refresh(): Promise<void> {
    await Promise.all(["", ...Object.keys(this.opened)].map((path) => this.load(path)));
    for (const path of Object.keys(this.opened)) if (!this.shown(path)) delete this.opened[path];
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
