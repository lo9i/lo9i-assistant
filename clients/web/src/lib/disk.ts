// The disk lo9i takes by category (src/lo9i/core/disk/), drawn as one bar of its parts, largest first, with what
// cleaning each frees.
import type { DiskCategory } from "./api/types";
import { formatNumber, t, type Key } from "./i18n.svelte";

const NAMES: Record<string, Key> = {
  database: "disk.names.database",
  models: "disk.names.models",
  plugins: "disk.names.plugins",
  browsers: "disk.names.browsers",
  plugin_data: "disk.names.plugin_data",
  uploads: "disk.names.uploads",
  logs: "disk.names.logs",
  workspace: "disk.names.workspace",
  backups: "disk.names.backups",
  downloads: "disk.names.downloads",
  other: "disk.names.other",
};

// What cleaning a category removes; one that has nothing to clean isn't here.
const CLEANS: Record<string, Key> = {
  database: "disk.cleans.database",
  logs: "disk.cleans.logs",
  backups: "disk.cleans.backups",
  uploads: "disk.cleans.uploads",
  plugins: "disk.cleans.plugins",
  plugin_data: "disk.cleans.plugin_data",
  downloads: "disk.cleans.downloads",
};

export function categoryName(name: string): string {
  return NAMES[name] ? t(NAMES[name]) : name;
}

export function cleans(name: string): string {
  return CLEANS[name] ? t(CLEANS[name]) : "";
}

const UNITS = ["B", "KB", "MB", "GB", "TB"];

/** Like "1.4 GB" or "512 KB", in powers of 1024 as the system's disk tools count. */
export function diskSize(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${formatNumber(value, { maximumFractionDigits: unit && value < 100 ? 1 : 0 })} ${UNITS[unit]}`;
}

export type Segment = DiskCategory & { share: number; start: number };

/** The categories that take anything, largest first, each with its share of `total` and where it starts in the bar,
 * both as fractions of it. */
export function segments(categories: DiskCategory[], total: number): Segment[] {
  let start = 0;
  return categories
    .filter((c) => c.bytes > 0)
    .sort((a, b) => b.bytes - a.bytes)
    .map((c) => {
      const share = total ? c.bytes / total : 0;
      const segment = { ...c, share, start };
      start += share;
      return segment;
    });
}

/** What Clean up frees: every category but those cleaned only when named. */
export function cleanedTogether(categories: DiskCategory[]): DiskCategory[] {
  return categories.filter((c) => c.freeable > 0 && !c.on_request);
}
