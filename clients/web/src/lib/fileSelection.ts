// The Files page's picks: the files ticked on the page shown, to delete together.
import { pageCount } from "./paging";

/** The picks with `path` ticked or not, each once. */
export function ticked(picks: string[], path: string, on: boolean): string[] {
  const others = picks.filter((p) => p !== path);
  return on ? [...others, path] : others;
}

/** The picks with every one of `shown` ticked or none of them; picks not shown are left as they are. */
export function tickedAll(picks: string[], shown: string[], on: boolean): string[] {
  const others = picks.filter((p) => !shown.includes(p));
  return on ? [...others, ...shown] : others;
}

/** The picks still shown: a file deleted, or gone from the page as the list changed, isn't picked any more. */
export function stillShown(picks: string[], shown: string[]): string[] {
  return picks.filter((p) => shown.includes(p));
}

/** The page to show when the one shown came back empty (its last files deleted): the last one there is. */
export function pageWithFiles(page: number, total: number, size: number): number {
  return Math.min(page, pageCount(total, size) - 1);
}
