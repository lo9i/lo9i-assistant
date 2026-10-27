// Answer buttons: a reply that ends with a question with a few clear answers lists them in a marker at its end,
// `<!-- choices: Yes | No -->` (src/assistant/core/conversation/choices.py, prompts/operating.md). The marker never
// shows; its choices show as buttons under the reply.

const MARKER = /<!--\s*choices:[\s\S]*?-->/gi;
// A comment still open at the end, or its first characters: while the reply streams it may become a marker.
const OPENING = /(<!--(?:(?!-->)[\s\S])*|<!-?)$/;
const ENDING = /<!--\s*choices:([\s\S]*?)-->\s*$/i;

export type Answerable = { text: string; choices: string[] };

/** `text` as the user reads it, and the choices its marker at the end lists (none without one). */
export function answerable(text: string): Answerable {
  const choices = (ENDING.exec(text)?.[1] ?? "")
    .split("|")
    .map((choice) => choice.trim())
    .filter(Boolean);
  return { text: withoutMarkers(text), choices };
}

/** `text` without its markers, nor what may be the start of one at its end. */
export function withoutMarkers(text: string): string {
  return text.replace(MARKER, "").replace(OPENING, "").trimEnd();
}
