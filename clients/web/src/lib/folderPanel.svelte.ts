// Whether the side panel with a folder's files (ui/chat/folder/HandedFolder.svelte) is shown: the handed folder's
// beside a conversation with an agent, the home folder's beside any other. Each kept per browser; storage can be
// unavailable. The handed folder's starts shown, as it's what the agent works on; the home folder's starts hidden,
// as it's there in every conversation. A narrow screen starts with both hidden, whatever was kept: they cover the
// chat there.
export const NARROW = "(max-width: 900px)";

class FolderPanel {
  open = $state(false);

  constructor(
    private readonly key: string,
    shownAtFirst: boolean,
  ) {
    this.open = initial(key, shownAtFirst);
  }

  toggle(): void {
    this.open = !this.open;
    try {
      localStorage.setItem(this.key, this.open ? "open" : "closed");
    } catch {
      // Kept for this page only.
    }
  }
}

function initial(key: string, shownAtFirst: boolean): boolean {
  try {
    if (window.matchMedia(NARROW).matches) return false;
    const kept = localStorage.getItem(key);
    return kept === null ? shownAtFirst : kept === "open";
  } catch {
    return shownAtFirst;
  }
}

export const folderPanel = new FolderPanel("lo9i.folderPanel", true);
export const homePanel = new FolderPanel("lo9i.homePanel", false);
