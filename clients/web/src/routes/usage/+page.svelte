<script lang="ts">
  import ChartColumn from "@lucide/svelte/icons/chart-column";
  import type { ToolUsage } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TokenUsage from "$lib/ui/TokenUsage.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  type Kind = "tool" | "skill";
  type Filter = "all" | Kind;
  const PERIODS = [7, 30, 90];
  const FILTERS: { id: Filter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "tool", label: "Tools" },
    { id: "skill", label: "Skills" },
  ];
  const KINDS: Record<Kind, string> = { tool: "Tool", skill: "Skill" };

  let days = $state(7);
  let filter = $state<Filter>("all");
  const report = resource((c) => c.usage.report(days), ["run_finished"]);
  // Tools and skills in one list, most used first.
  const rows = $derived.by(() => {
    if (!report.data) return undefined;
    const all: (ToolUsage & { kind: Kind })[] = [
      ...report.data.tools.map((r) => ({ ...r, kind: "tool" as const })),
      ...report.data.skills.map((r) => ({ ...r, kind: "skill" as const })),
    ];
    return all.filter((r) => filter === "all" || r.kind === filter).sort((a, b) => b.calls - a.calls);
  });

  function seconds(ms: number): string {
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  }
</script>

<TopBar title="Usage">
  {#snippet actions()}
    <div class="tabs" role="radiogroup" aria-label="Period">
      {#each PERIODS as d (d)}
        <button role="radio" aria-checked={d === days} class:active={d === days} onclick={() => (days = d)}>{d} days</button>
      {/each}
    </div>
  {/snippet}
</TopBar>

<div class="shell">
  <TokenUsage {days} />
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Tool and skill calls</h2>
        <p class="text-meta">How often the assistant used each one in the last {days} days.</p>
      </div>
      <div class="controls">
        <div class="tabs" role="radiogroup" aria-label="Show">
          {#each FILTERS as f (f.id)}
            <button role="radio" aria-checked={f.id === filter} class:active={f.id === filter} onclick={() => (filter = f.id)}>
              {f.label}
            </button>
          {/each}
        </div>
        {#if rows}<span class="pill">{rows.length}</span>{/if}
      </div>
    </header>
    {#if report.error}
      <p class="error-text pad">{report.error}</p>
    {:else if rows?.length === 0}
      <EmptyState icon={ChartColumn} title="Not used yet" text="Nothing in the last {days} days." />
    {:else if rows}
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
            <th>Name</th>
            <th>Type</th>
            <th class="num">Calls</th>
            <th class="num">Errors</th>
            <th class="num">Denied</th>
            <th class="num">Avg time</th>
            <th class="when hide-narrow">Last used</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as r (`${r.kind}-${r.name}`)}
            <tr>
              <td class="name">{r.name}</td>
              <td><span class="pill">{KINDS[r.kind]}</span></td>
              <td class="num">{r.calls}</td>
              <td class="num">{r.errors}</td>
              <td class="num">{r.denied}</td>
              <td class="num">{seconds(r.avg_ms)}</td>
              <td class="when text-label hide-narrow">{new Date(r.last_used).toLocaleString()}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </section>
</div>

<style>
  .shell {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 16px 16px 40px;
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
    .toolbar {
      flex-direction: column;
      align-items: flex-start;
    }
  }
</style>
