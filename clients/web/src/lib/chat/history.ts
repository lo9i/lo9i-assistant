// Up and Down in the message box go through the messages sent in this conversation, like a shell's
// history: Up from the box steps back, Down steps forward and past the newest returns what was being typed.

/** The texts to go through, oldest first: the user's messages with text, a repeat in a row once. */
export function sentTexts(items: ReadonlyArray<{ kind: string; text?: string }>): string[] {
  const texts = items.filter((i) => i.kind === "user" && i.text?.trim()).map((i) => i.text!.trim());
  return texts.filter((text, i) => text !== texts[i - 1]);
}

/** Which sent message to show after Up (-1) or Down (+1): its index, or null for what was being typed. */
export function step(count: number, at: number | null, direction: -1 | 1): number | null {
  if (count === 0) return null;
  if (at === null) return direction === -1 ? count - 1 : null;
  const next = at + direction;
  if (next >= count) return null;
  return Math.max(0, next);
}

/** Up acts on the box's first line and Down on its last, so the keys still move through a long message. */
export function onEdgeLine(text: string, caret: number, direction: -1 | 1): boolean {
  return direction === -1 ? !text.slice(0, caret).includes("\n") : !text.slice(caret).includes("\n");
}
