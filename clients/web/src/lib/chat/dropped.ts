// Files dragged onto the chat from the computer, attached like the paperclip's.

/** Whether a drag carries files (not text or a link), so the chat offers to take it. */
export function carriesFiles(data: DataTransfer | null): boolean {
  return Boolean(data && Array.from(data.types).includes("Files"));
}

/** The dropped files, and how many folders were left out: a browser can't read a folder as one file. */
export function droppedFiles(data: DataTransfer): { files: File[]; folders: number } {
  const items = Array.from(data.items ?? []).filter((item) => item.kind === "file");
  if (items.length === 0) return { files: Array.from(data.files), folders: 0 };
  const isFolder = (item: DataTransferItem) => item.webkitGetAsEntry?.()?.isDirectory ?? false;
  const files = items.filter((item) => !isFolder(item)).map((item) => item.getAsFile());
  return { files: files.filter((f): f is File => f !== null), folders: items.length - files.length };
}
