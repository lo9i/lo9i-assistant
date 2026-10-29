<script lang="ts">
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import type { ToolUsage } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import { formatDate, formatNumber, t, type Key } from "$lib/i18n.svelte";
  import { pageOf } from "$lib/paging";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import Pager from "$lib/ui/Pager.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TokenUsage from "$lib/ui/TokenUsage.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  type Kind = "tool" | "skill";
  type Filter = "all" | Kind;
  const PERIODS = [7, 30, 90];
  const FILTERS: { id: Filter; label: Key }[] = [
    { id: "all", label: "usagePage.all" },
    { id: "tool", label: "usagePage.tools" },
    { id: "skill", label: "usagePage.skills" },
  ];
  const KINDS: Record<Kind, Key> = { tool: "tokens.tool", skill: "tokens.skill" };
  const PAGE_SIZE = 20;

  let days = $state(7);
  let filter = $state<Filter>("all");
  let query = $state("");
  let page = $state(0);
  const report = resource((c) => c.usage.report(days), ["run_finished"]);
  // Tools and skills in one list, most used first.
  const rows = $derived.by(() => {
    if (!report.data) return undefined;
    const all: (ToolUsage & { kind: Kind })[] = [
      ...report.data.tools.map((r) => ({ ...r, kind: "tool" as const })),
      ...report.data.skills.map((r) => ({ ...r, kind: "skill" as const })),
    ];
    const words = query.trim().toLowerCase();
    return all
      .filter((r) => (filter === "all" || r.kind === filter) && r.name.toLowerCase().includes(words))
      .sort((a, b) => b.calls - a.calls);
  });
  const shown = $derived(rows && pageOf(rows, page, PAGE_SIZE));

  // A new period, filter or search starts from the first page.
  $effect(() => {
    void [days, filter, query];
    page = 0;
  });

  function seconds(ms: number): string {
    return ms < 1000 ? `${ms} ms` : `${formatNumber(ms / 1000, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
  }
</script>

<TopBar title={t("nav.usage")}>
  {#snippet actions()}
    <div class="tabs" role="radiogroup" aria-label={t("usagePage.period")}>
      {#each PERIODS as d (d)}
        <button role="radio" aria-checked={d === days} class:active={d === days} onclick={() => (days = d)}
          >{t("usagePage.days", { days: d })}</button
        >
      {/each}
    </div>
  {/snippet}
</TopBar>

<div class="shell">
  <TokenUsage {days} />
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("usagePage.title")}</h2>
        <p class="text-meta">{t("usagePage.hint", { days })}</p>
      </div>
      <div class="controls">
        <SearchField bind:value={query} label={t("usagePage.search")} />
        <div class="tabs" role="radiogroup" aria-label={t("usagePage.show")}>
          {#each FILTERS as f (f.id)}
            <button role="radio" aria-checked={f.id === filter} class:active={f.id === filter} onclick={() => (filter = f.id)}>
              {t(f.label)}
            </button>
          {/each}
        </div>
        {#if rows}<span class="pill">{rows.length}</span>{/if}
      </div>
    </header>
    {#if report.error}
      <p class="error-text pad">{report.error}</p>
    {:else if rows?.length === 0 && query.trim()}
      <EmptyState icon={ChartColumn} title={t("usagePage.noMatches")} text={t("usagePage.noMatchesHint", { days, query: query.trim() })} />
    {:else if rows?.length === 0}
      <EmptyState icon={ChartColumn} title={t("usagePage.notUsed")} text={t("usagePage.notUsedHint", { days })} />
    {:else if rows && shown}
      <table class="data-table">
        <colgroup>
          <col />
          <col class="type" />
          <col class="n" />
          <col class="n" />
          <col class="n" />
          <col class="n" />
          <col class="when hide-narrow" />
        </colgroup>
        <thead>
          <tr>
            <th>{t("alerts.name")}</th>
            <th>{t("files.type")}</th>
            <th class="num">{t("tokens.calls")}</th>
            <th class="num">{t("usagePage.errors")}</th>
            <th class="num">{t("usagePage.denied")}</th>
            <th class="num">{t("usagePage.avgTime")}</th>
            <th class="when hide-narrow">{t("devices.lastUsed")}</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as r (`${r.kind}-${r.name}`)}
            <tr>
              <td class="name">{r.name}</td>
              <td><span class="pill">{t(KINDS[r.kind])}</span></td>
              <td class="num">{r.calls}</td>
              <td class="num">{r.errors}</td>
              <td class="num">{r.denied}</td>
              <td class="num">{seconds(r.avg_ms)}</td>
              <td class="when text-label hide-narrow">{formatDate(r.last_used, { dateStyle: "medium", timeStyle: "short" })}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if rows.length > PAGE_SIZE}<Pager bind:page total={rows.length} size={PAGE_SIZE} />{/if}
    {/if}
  </section>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 0 16px 40px;
    max-width: 1600px;
    margin: 0 auto;
  }
  .table-card {
    overflow: hidden;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .pad {
    padding: 24px;
  }
  table {
    table-layout: fixed;
  }
  col.type {
    width: 100px;
  }
  col.n {
    width: 110px;
  }
  col.when {
    width: 252px;
  }
  .data-table .when {
    padding-left: 32px;
  }
  .name {
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  @media (max-width: 680px) {
    .toolbar,
    .controls {
      flex-direction: column;
      align-items: flex-start;
    }
  }
</style>
