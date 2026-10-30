<script lang="ts">
  import Coins from "@lucide/svelte/icons/coins";
  import type { TokenReport, TokenRow } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import { formatNumber, t, type Key } from "$lib/i18n.svelte";
  import EmptyState from "./EmptyState.svelte";
  import TokenLine from "./TokenLine.svelte";
  import TokenBars from "./TokenBars.svelte";
  import Activity from "@lucide/svelte/icons/activity";
  import ArrowDownToLine from "@lucide/svelte/icons/arrow-down-to-line";
  import ArrowUpFromLine from "@lucide/svelte/icons/arrow-up-from-line";
  import CircleDollarSign from "@lucide/svelte/icons/circle-dollar-sign";

  let { days }: { days: number } = $props();

  type Group = "by_model" | "by_purpose" | "by_conversation" | "by_job" | "by_skill" | "by_tool" | "by_channel" | "by_day";
  const GROUPS: { id: Group; label: Key; column: Key }[] = [
    { id: "by_model", label: "tokens.model", column: "tokens.model" },
    { id: "by_purpose", label: "tokens.purpose", column: "tokens.purpose" },
    { id: "by_conversation", label: "tokens.conversation", column: "tokens.conversation" },
    { id: "by_job", label: "tokens.job", column: "tokens.job" },
    { id: "by_skill", label: "tokens.skill", column: "tokens.skillInUse" },
    { id: "by_tool", label: "tokens.tool", column: "tokens.tool" },
    { id: "by_channel", label: "tokens.channel", column: "tokens.channel" },
    { id: "by_day", label: "tokens.day", column: "tokens.day" },
  ];
  const PURPOSES: Record<string, Key> = {
    reply: "tokens.replies",
    summary: "tokens.summaries",
    title: "tokens.titles",
    check: "tokens.checks",
  };

  // Output and cost each have a colour of their own, so the tiles read apart at a glance.
  const OUTPUT_COLOR = "var(--color-brand)";
  const COST_COLOR = "var(--color-warn)";

  let group = $state<Group>("by_model");
  const report = resource((c) => c.usage.tokens(days), ["run_finished"]);
  const total = $derived(report.data?.total);
  const rows = $derived<TokenRow[]>((report.data as TokenReport | undefined)?.[group] ?? []);
  const column = $derived.by(() => {
    const found = GROUPS.find((g) => g.id === group);
    return found ? t(found.column) : "";
  });
  // Tools' share of a call can't be priced: which cache price applied to it isn't known.
  const priced = $derived(group !== "by_tool");

  function count(tokens: number): string {
    const one = (n: number) => formatNumber(n, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    if (tokens >= 1_000_000) return `${one(tokens / 1_000_000)}M`;
    return tokens >= 1000 ? `${one(tokens / 1000)}k` : String(tokens);
  }

  // One point per day of the period, days without calls at 0.
  function series(key: "input_tokens" | "output_tokens" | "calls" | "cost") {
    const byDay = new Map(((report.data as TokenReport | undefined)?.by_day ?? []).map((r) => [r.name, r[key] ?? 0]));
    const out: { day: string; value: number }[] = [];
    const now = new Date();
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      out.push({ day, value: byDay.get(day) ?? 0 });
    }
    return out;
  }
  const inputSeries = $derived(series("input_tokens"));
  const outputSeries = $derived(series("output_tokens"));
  const callSeries = $derived(series("calls"));
  const costSeries = $derived(series("cost"));

  function money(dollars: number | null | undefined): string {
    return dollars == null ? t("tokens.noPrice") : formatNumber(dollars, { style: "currency", currency: "USD" });
  }

  function name(row: TokenRow): string {
    if (group === "by_purpose") return row.name in PURPOSES ? t(PURPOSES[row.name]) : row.name;
    return row.label || row.name;
  }
</script>

{#if report.error}
  <p class="error-text">{report.error}</p>
{:else if total}
  <div class="tiles">
    <div class="tile surface--glass">
      <span class="tile-head"><Activity size={15} class="tile-icon" aria-hidden="true" />{t("tokens.modelCalls")}</span>
      <div class="tile-body">
        <span class="big">{formatNumber(total.calls)}</span>
        <div class="chart"><TokenBars points={callSeries} label={t("tokens.modelCallsPerDay")} /></div>
      </div>
      <span class="text-caption"
        >{report.data?.estimated_calls
          ? t("tokens.estimated", { count: report.data.estimated_calls })
          : t("tokens.lastDays", { days })}</span
      >
    </div>
    <div class="tile surface--glass">
      <span class="tile-head"><ArrowDownToLine size={15} class="tile-icon" aria-hidden="true" />{t("tokens.inputTokens")}</span>
      <div class="tile-body">
        <span class="big">{count(total.input_tokens)}</span>
        <div class="chart"><TokenLine points={inputSeries} label={t("tokens.inputPerDay")} /></div>
      </div>
      <span class="text-caption">
        {t("tokens.fromCachePercent", {
          percent: total.input_tokens ? Math.round((100 * total.cache_read_tokens) / total.input_tokens) : 0,
        })}
      </span>
    </div>
    <div class="tile surface--glass" style:--tile-color={OUTPUT_COLOR}>
      <span class="tile-head"><ArrowUpFromLine size={15} class="tile-icon" aria-hidden="true" />{t("tokens.outputTokens")}</span>
      <div class="tile-body">
        <span class="big">{count(total.output_tokens)}</span>
        <div class="chart"><TokenLine points={outputSeries} label={t("tokens.outputPerDay")} color={OUTPUT_COLOR} /></div>
      </div>
      <span class="text-caption">{t("tokens.outputHint")}</span>
    </div>
    <div class="tile surface--glass" style:--tile-color={COST_COLOR}>
      <span class="tile-head"><CircleDollarSign size={15} class="tile-icon" aria-hidden="true" />{t("tokens.cost")}</span>
      <div class="tile-body">
        <span class="big">{money(total.cost)}</span>
        <div class="chart"><TokenLine points={costSeries} label={t("tokens.costPerDay")} color={COST_COLOR} /></div>
      </div>
      <span class="text-caption">{t("tokens.costHint")}</span>
    </div>
  </div>

  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("tokens.title")}</h2>
        <p class="text-meta">
          {group === "by_tool" ? t("tokens.byToolHint") : group === "by_skill" ? t("tokens.bySkillHint") : t("tokens.hint", { days })}
        </p>
      </div>
      <div class="tabs" role="radiogroup" aria-label={t("tokens.groupBy")}>
        {#each GROUPS as g (g.id)}
          <button role="radio" aria-checked={g.id === group} class:active={g.id === group} onclick={() => (group = g.id)}
            >{t(g.label)}</button
          >
        {/each}
      </div>
    </header>
    {#if rows.length === 0}
      <EmptyState icon={Coins} title={t("tokens.nothingYet")} text={t("tokens.nothingYetHint", { days })} />
    {:else}
      <table class="data-table">
        <thead>
          <tr>
            <th>{column}</th>
            <th class="num">{t("tokens.calls")}</th>
            <th class="num">{t("tokens.input")}</th>
            {#if priced}<th class="num">{t("tokens.fromCache")}</th>{/if}
            <th class="num">{t("tokens.output")}</th>
            {#if priced}<th class="num">{t("tokens.cost")}</th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each rows as row (row.name)}
            <tr>
              <td class="name" title={row.name}>{name(row)}</td>
              <td class="num">{row.calls}</td>
              <td class="num">{count(row.input_tokens)}</td>
              {#if priced}<td class="num">{count(row.cache_read_tokens)}</td>{/if}
              <td class="num">{count(row.output_tokens)}</td>
              {#if priced}<td class="num">{money(row.cost)}</td>{/if}
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
{:else}
  <p class="text-meta">{t("common.loading")}</p>
{/if}

<style>
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 16px;
    border-radius: 12px;
  }
  .tile-head {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.875rem;
    font-weight: 500;
  }
  .tile-head :global(.tile-icon) {
    color: var(--tile-color, var(--color-accent, #f59e0b));
  }
  .tile-body {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .big {
    font-size: 1.6rem;
    font-weight: 600;
    line-height: 1;
    white-space: nowrap;
  }
  .chart {
    flex: 0 1 45%;
    min-width: 60px;
    max-height: 40px;
  }
  .table-card {
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
    max-width: 60ch;
  }
  .name {
    font-weight: 500;
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  @media (max-width: 900px) {
    .tiles {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
