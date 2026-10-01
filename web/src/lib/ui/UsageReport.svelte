<script lang="ts">
  import type { ToolUsage } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import SettingsCard from "./Card.svelte";

  const PERIODS = [7, 30, 90];
  let days = $state(7);
  const report = resource((c) => c.usage.report(days), ["run_finished"]);

  function seconds(ms: number): string {
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
  }
</script>

{#snippet table(rows: ToolUsage[], label: string)}
  {#if rows.length === 0}
    <p class="text-meta">None yet.</p>
  {:else}
    <div class="table-box">
      <table class="data-table">
        <thead>
          <tr><th>{label}</th><th class="num">Calls</th><th class="num">Errors</th><th class="num">Denied</th><th class="num">Avg time</th><th>Last used</th></tr>
        </thead>
        <tbody>
          {#each rows as r (r.name)}
            <tr>
              <td>{r.name}</td>
              <td class="num">{r.calls}</td>
              <td class="num">{r.errors}</td>
              <td class="num">{r.denied}</td>
              <td class="num">{seconds(r.avg_ms)}</td>
              <td class="text-label">{new Date(r.last_used).toLocaleString()}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
{/snippet}

<SettingsCard id="usage" title="Tools and skills" sub="How often the assistant used each one.">
  {#snippet status()}
    <div class="tabs" role="radiogroup" aria-label="Period">
      {#each PERIODS as d (d)}
        <button role="radio" aria-checked={d === days} class:active={d === days} onclick={() => (days = d)}>{d} days</button>
      {/each}
    </div>
  {/snippet}
  {#if report.error}<p class="error-text">{report.error}</p>{/if}
  {#if report.data}
    <h3 class="micro-label">Tools</h3>
    {@render table(report.data.tools, "Tool")}
    <h3 class="micro-label">Skills</h3>
    {@render table(report.data.skills, "Skill")}
  {/if}
</SettingsCard>

<style>
  h3 {
    margin: 0 0 -12px;
  }
  .table-box {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }
  p {
    margin: 0;
  }
</style>
