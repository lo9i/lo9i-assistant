/** A period the Usage page shows: today, from local midnight, or the last so many days. */
export type UsagePeriod = "today" | number;

export const USAGE_PERIODS: UsagePeriod[] = ["today", 7, 30, 90];

/** What the daemon is asked for: the days and, for today, where the report starts, midnight in this browser's
 * timezone, worked out at each load so a page left open past midnight starts the new day. */
export function usageRange(period: UsagePeriod, now = new Date()): { days: number; since?: Date } {
  if (period !== "today") return { days: period };
  return { days: 1, since: new Date(now.getFullYear(), now.getMonth(), now.getDate()) };
}
