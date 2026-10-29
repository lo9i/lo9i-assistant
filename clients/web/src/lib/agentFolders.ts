// The /claude folder picker (ui/chat/AgentFolderModal.svelte): what it offers at each point, from what the daemon
// listed (src/assistant/core/conversation/agent_folders.py). Picking a folder hands the conversation to the agent
// there; browsing lists the folders inside one.
import type { AgentFolders, FolderListing } from "./api/types";
import { t } from "./i18n.svelte";

/** A button: `pick` hands over that folder, `browse` lists the folders inside it. */
export type FolderChoice = { label: string; path: string; action: "pick" | "browse"; up?: boolean; detail?: string };

export type FolderView = {
  description: string;
  choices: FolderChoice[];
  // The footer's main button, once there's something to offer.
  primary: FolderChoice | null;
  // Browsing a folder with nothing inside.
  empty: boolean;
};

/** Before browsing: the workspace and the folders used before, and Browse… from the home folder. While browsing:
 * Up, the folders inside, and Use this folder. */
export function folderView(folders: AgentFolders | null, listing: FolderListing | null): FolderView {
  if (listing) return browsing(listing);
  if (!folders) return { description: t("folders.starting"), choices: [], primary: null, empty: false };
  const workspace: FolderChoice = { label: t("folders.workspace"), path: folders.workspace, action: "pick", detail: folders.workspace };
  const recent = folders.recent.map((path): FolderChoice => ({ label: path, path, action: "pick" }));
  const browse: FolderChoice = { label: t("folders.browse"), path: folders.home, action: "browse" };
  return { description: t("folders.starting"), choices: [workspace, ...recent], primary: browse, empty: false };
}

function browsing(listing: FolderListing): FolderView {
  const up: FolderChoice[] = listing.parent ? [{ label: t("folders.up"), path: listing.parent, action: "browse", up: true }] : [];
  const inside = listing.children.map((path): FolderChoice => ({ label: lastPart(path), path, action: "browse" }));
  const use: FolderChoice = { label: t("folders.use"), path: listing.path, action: "pick" };
  return { description: listing.path, choices: [...up, ...inside], primary: use, empty: inside.length === 0 };
}

function lastPart(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? path;
}
