<script lang="ts">
  import { resolve } from "$app/paths";
  import Bell from "@lucide/svelte/icons/bell";
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import type { Alert } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { localTime } from "$lib/health";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { client, notices } = useDaemon();
  // Failures are stored with the servers and skills, so their events refresh the list.
  const alerts = resource((c) => c.alerts.list(), ["mcp", "skills"]);
  let picked = $state<string | null>(null);
  // Until one is picked: the newest.
  const alert = $derived(alerts.data?.find((a) => key(a) === picked) ?? alerts.data?.[0]);

  function key(a: Alert): string {
    return `${a.area}/${a.name}`;
  }

  function kind(a: Alert): string {
    return a.area === "mcp" ? "MCP server" : "Skill";
  }

  /** Failures in a row, or that a remote server waits for the user to sign in again. */
  function problem(a: Alert): string {
    return a.kind === "signed_out" ? "Sign in again" : `${a.failures} in a row`;
  }

  function href(a: Alert): string {
    return `${a.area === "mcp" ? resolve("/mcp") : resolve("/skills")}?s=${encodeURIComponent(a.name)}`;
  }

  async function dismiss(a: Alert): Promise<void> {
    try {
      await client.alerts.dismiss(a.area, a.name);
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<TopBar title="Alerts" />

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">Needs attention</h2>
        <p class="text-meta">MCP servers and skills that keep failing or need you to sign in again. Click one to see it on the right.</p>
      </div>
      {#if alerts.data}<span class="pill">{alerts.data.length}</span>{/if}
    </header>
    <div class="scroll">
      {#if alerts.error}
        <p class="error-text pad">{alerts.error}</p>
      {:else if alerts.data?.length === 0}
        <EmptyState
          icon={CircleCheck}
          title="Nothing needs attention"
          text="MCP servers and skills that keep failing, and servers that need you to sign in again, show up here."
        />
      {:else if alerts.data && alert}
        <table class="data-table">
          <thead><tr><th>Name</th><th class="hide-narrow">Kind</th><th>Problem</th><th class="hide-narrow">When</th></tr></thead>
          <tbody>
            {#each alerts.data as a (key(a))}
              <tr class:selected={key(a) === key(alert)} onclick={() => (picked = key(a))}>
                <td><button class="row-button" onclick={() => (picked = key(a))}>{a.name}</button></td>
                <td class="text-label hide-narrow">{kind(a)}</td>
                <td class="text-label">{problem(a)}</td>
                <td class="text-label hide-narrow">{localTime(a.at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if alert}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{alert.name}</h2>
          <span class="pill pill--danger">{alert.kind === "signed_out" ? "signed out" : "failing"}</span>
        </header>
        <dl>
          <dt class="micro-label">Kind</dt>
          <dd>{kind(alert)}</dd>
          <dt class="micro-label">Problem</dt>
          <dd>{problem(alert)}</dd>
          <dt class="micro-label">When</dt>
          <dd>{localTime(alert.at)}</dd>
        </dl>
        <pre class="error">{alert.error}</pre>
        <div class="actions">
          <a class="btn btn--neutral btn--sm" href={href(alert)}>Open</a>
          <button class="btn btn--ghost btn--sm" onclick={() => dismiss(alert)}>Dismiss</button>
        </div>
      </section>
    {:else}
      <section class="details surface--glass">
        <EmptyState
          icon={Bell}
          title="No alert selected"
          text="Alerts show here when something keeps failing or needs you to sign in again."
        />
      </section>
    {/if}
  </div>
</div>

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 16px;
    height: calc(100dvh - 76px);
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the alert the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
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
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }
  .details {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
  }
  .details header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
  }
  .error {
    margin: 0;
    padding: 12px;
    max-height: 240px;
    overflow: auto;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-danger) 8%, transparent);
    color: var(--color-text-primary);
    font-size: var(--font-size-xs);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  /* Stacked, the page scrolls: each part takes its own height instead of a share of the screen. */
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
    }
  }
</style>
