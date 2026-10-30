// Whether the side panel with the handed folder's files (ui/chat/folder/HandedFolder.svelte) is shown. Kept per
// browser; storage can be unavailable. A narrow screen starts with it hidden, whatever was kept: it covers the chat
// there.
const KEY = "lo9i.folderPanel";
export const NARROW = "(max-width: 900px)";

class FolderPanel {
  open = $state(initial());

  toggle(): void {
    this.open = !this.open;
    try {
      localStorage.setItem(KEY, this.open ? "open" : "closed");
    } catch {
      // Kept for this page only.
    }
  }
}

function initial(): boolean {
  try {
    if (window.matchMedia(NARROW).matches) return false;
    return localStorage.getItem(KEY) !== "closed";
  } catch {
    return true;
  }
}

export const folderPanel = new FolderPanel();
