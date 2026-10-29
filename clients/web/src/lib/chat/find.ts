// Finding text in the open conversation (Cmd+F / Ctrl+F), as a browser's find bar does: every match, case
// aside, one of them the current one. The whole history is on the page, so the page's text is the conversation's.

/** Where a match is in a run of texts: each end as [which text, offset in it], the end one past its last letter. */
export type Span = { start: [number, number]; end: [number, number] };

type Keys = Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey">;

/** Cmd+F on a Mac, Ctrl+F elsewhere. */
export function isFindKey(e: Keys, mac: boolean): boolean {
  const command = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
  return command && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "f";
}

/** Whether this browser runs on Apple's systems, where shortcuts take Cmd. */
export function onMac(platform: string): boolean {
  return /mac|iphone|ipad/i.test(platform);
}

/** The matches of `query` in `texts` read as one text, so a match may cross the elements bold or a link start. */
export function locate(texts: readonly string[], query: string): Span[] {
  if (!query) return [];
  const starts: number[] = [];
  let length = 0;
  for (const text of texts) {
    starts.push(length);
    length += text.length;
  }
  const pattern = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
  return [...texts.join("").matchAll(pattern)].map((m) => ({
    start: at(starts, m.index),
    end: inclusiveEnd(starts, m.index + m[0].length),
  }));
}

/** The text holding the letter at `index`, and where in it. */
function at(starts: readonly number[], index: number): [number, number] {
  let i = starts.length - 1;
  while (i > 0 && starts[i] > index) i--;
  return [i, index - starts[i]];
}

/** The end of a match in the text of its last letter, never at the start of the next. */
function inclusiveEnd(starts: readonly number[], end: number): [number, number] {
  const [i, offset] = at(starts, end - 1);
  return [i, offset + 1];
}

/** The match after `current` (`direction` 1) or before it (-1), going round at either end; -1 with none. */
export function step(current: number, count: number, direction: 1 | -1): number {
  if (count === 0) return -1;
  return (current + direction + count) % count;
}

/** The first match at or below `top` (where the reader is), each match given by its top; the last when all are
 * above, -1 with none. */
export function nearest(tops: readonly number[], top: number): number {
  if (tops.length === 0) return -1;
  const below = tops.findIndex((t) => t >= top);
  return below === -1 ? tops.length - 1 : below;
}

/** "3 of 12", or why there's nothing to step through. */
export function counter(current: number, count: number, query: string): string {
  if (!query) return "";
  if (count === 0) return "No results";
  return `${current + 1} of ${count}`;
}
