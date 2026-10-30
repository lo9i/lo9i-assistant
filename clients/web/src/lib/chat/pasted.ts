// Files pasted into the message box, like Ctrl+V in the terminal app (src/assistant/client/clipboard/).

// What browsers call image data pasted without a file, such as a screenshot.
const UNNAMED_IMAGE = "image.png";

/** The files in a paste, or none when it's only text, which the message box takes as usual. Some browsers leave
 * `files` empty for a pasted screenshot and give it only as an item. */
export function pastedFiles(data: DataTransfer, now: Date = new Date()): File[] {
  const files = data.files.length ? Array.from(data.files) : itemFiles(data);
  return files.map((file) => (file.name === UNNAMED_IMAGE ? renamed(file, now) : file));
}

function itemFiles(data: DataTransfer): File[] {
  return Array.from(data.items)
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null);
}

function renamed(file: File, now: Date): File {
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()].map((n) => String(n).padStart(2, "0")).join("");
  return new File([file], `pasted-${time}.png`, { type: file.type });
}
