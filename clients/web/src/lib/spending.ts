// The spending limits as Settings → Model edits them (ui/settings/SpendingLimitsCard.svelte): each a field holding
// an amount in US dollars, empty for no limit.
import type { SpendingLimits } from "$lib/api/types";

export const LIMITS = ["job_run", "job_day", "conversation", "day"] as const;
export type Limit = (typeof LIMITS)[number];
export type LimitFields = Record<Limit, string>;

/** The limits as fields: an amount, or empty for none. */
export function fieldsOf(limits: SpendingLimits): LimitFields {
  return Object.fromEntries(LIMITS.map((limit) => [limit, limits[limit] == null ? "" : String(limits[limit])])) as LimitFields;
}

/** The limits the fields say, an empty one none; null when one isn't a number. Whether each is more than 0 the daemon
 * says. */
export function limitsOf(fields: LimitFields): SpendingLimits | null {
  const amounts = LIMITS.map((limit) => [limit, fields[limit].trim() === "" ? null : Number(fields[limit].trim())] as const);
  return amounts.some(([, amount]) => amount !== null && !Number.isFinite(amount)) ? null : (Object.fromEntries(amounts) as SpendingLimits);
}
