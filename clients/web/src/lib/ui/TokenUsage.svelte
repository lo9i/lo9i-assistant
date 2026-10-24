<script lang="ts">
  import Coins from "@lucide/svelte/icons/coins";
  import type { TokenReport, TokenRow } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import EmptyState from "./EmptyState.svelte";
  import TokenLine from "./TokenLine.svelte";

  let { days }: { days: number } = $props();

  type Group = "by_model" | "by_purpose" | "by_conversation" | "by_job" | "by_skill" | "by_tool" | "by_channel" | "by_day";
  const GROUPS: { id: Group; label: string; column: string }[] = [
    { id: "by_model", label: "Model", column: "Model" },
    { id: "by_purpose", label: "Purpose", column: "Purpose" },
    { id: "by_conversation", label: "Conversation", column: "Conversation" },
    { id: "by_job", label: "Job", column: "Job" },
    { id: "by_skill", label: "Skill", column: "Skill in use" },
    { id: "by_tool", label: "Tool", column: "Tool" },
    { id: "by_channel", label: "Channel", column: "Channel" },
    { id: "by_day", label: "Day", column: "Day" },
  ];
  const PURPOSES: Record<string, string> = {
    reply: "Replies",
    summary: "Summaries (compaction, archiving)",
    title: "Conversation titles",
    check: "Model checks",
  };

  let group = $state<Group>("by_model");
  const report = resource((c) => c.usage.tokens(days), ["run_finished"]);
  const total = $derived(report.data?.total);
  const rows = $derived<TokenRow[]>((report.data as TokenReport | undefined)?.[group] ?? []);
  const column = $derived(GROUPS.find((g) => g.id === group)?.column ?? "");
  // Tools' share of a call can't be priced: which cache price applied to it isn't known.
  const priced = $derived(group !== "by_tool");

  function count(tokens: number): string {
    if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
    return tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens);
  }

  // One point per day of the period, days without calls at 0.
  function series(key: "input_tokens" | "output_tokens") {
    const byDay = new Map(((report.data as TokenReport | undefined)?.by_day ?? []).map((r) => [r.name, r[key]]));
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

  function money(dollars: number | null | undefined): string {
    return dollars == null ? "No price" : `$${dollars.toFixed(2)}`;
  }

  function name(row: TokenRow): string {
    if (group === "by_purpose") return PURPOSES[row.name] ?? row.name;
    return row.label || row.name;
  }
</script>

{#if report.error}
  <p class="error-text">{report.error}</p>
{:else if total}
  <div class="tiles">
    <div class="tile surface--glass">
      <span class="micro-label">Model calls</span>
      <span class="value">{total.calls}</span>
      <span class="text-caption">
        {report.data?.estimated_calls ? `${report.data.estimated_calls} estimated (no usage reported)` : `last ${days} days`}
      </span>
    </div>
    <div class="tile surface--glass">
      <span class="micro-label">Input tokens</span>
      <TokenLine points={inputSeries} label="Input tokens per day" />
      <span class="text-caption">
        {count(total.input_tokens)} total · {total.input_tokens ? Math.round((100 * total.cache_read_tokens) / total.input_tokens) : 0}% from the cache
      </span>
    </div>
    <div class="tile surface--glass">
      <span class="micro-label">Output tokens</span>
      <TokenLine points={outputSeries} label="Output tokens per day" />
      <span class="text-caption">{count(total.output_tokens)} total · replies and tool calls</span>
    </div>
    <div class="tile surface--glass">
      <span class="micro-label">Cost</span>
      <span class="value">{money(total.cost)}</span>
      <span class="text-caption">models with a known price</span>
    </div>
  </div>

  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Tokens</h2>
        <p class="text-meta">
          {group === "by_tool"
            ? "What each tool's results and calls took. A result counts once, in the call right after the tool ran."
            : group === "by_skill"
              ? "Everything the calls cost while a skill was in use."
              : `What the model calls took in the last ${days} days.`}
        </p>
      </div>
      <div class="tabs" role="radiogroup" aria-label="Group by">
        {#each GROUPS as g (g.id)}
          <button role="radio" aria-checked={g.id === group} class:active={g.id === group} onclick={() => (group = g.id)}>{g.label}</button>
        {/each}
      </div>
    </header>
    {#if rows.length === 0}
      <EmptyState icon={Coins} title="Nothing here yet" text="No model calls in this group in the last {days} days." />
    {:else}
      <table class="data-table">
        <thead>
          <tr>
            <th>{column}</th>
            <th class="num">Calls</th>
            <th class="num">Input</th>
            {#if priced}<th class="num">From cache</th>{/if}
            <th class="num">Output</th>
            {#if priced}<th class="num">Cost</th>{/if}
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
  <p class="text-meta">Loading…</p>
{/if}

<style>
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 16px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 20px 24px;
  }
  .value {
    font-size: 28px;
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
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
