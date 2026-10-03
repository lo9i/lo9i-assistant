/** How many pages `total` items fill, at least one so an empty list still shows page 1 of 1. */
export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / size));
}

/** The items on page `page` (from 0), clamped to the last page when the list shrinks. */
export function pageOf<T>(items: T[], page: number, size: number): T[] {
  const last = pageCount(items.length, size) - 1;
  const start = Math.min(Math.max(page, 0), last) * size;
  return items.slice(start, start + size);
}
