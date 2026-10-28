<script lang="ts">
  import { onMount } from "svelte";
  import { resolve } from "$app/paths";
  import BellOff from "@lucide/svelte/icons/bell-off";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import type { Notification } from "$lib/api/types";
  import { pagedResource, resource, useDaemon } from "$lib/daemon.svelte";
  import { localTime } from "$lib/health";
  import { runQuery } from "$lib/jobs";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import ListEnd from "$lib/ui/ListEnd.svelte";
  import { installedIcon } from "$lib/pluginIcons";
  import PluginIcon from "$lib/ui/PluginIcon.svelte";
  import { openConversation } from "$lib/ui/openConversation";
  import TopBar from "$lib/ui/TopBar.svelte";

  // Scheduled jobs' results and background work that ended (core/notifications.py), apart from any
  // conversation. Each opens the conversation its work was started in, when it has one, and a job's run opens on
  // the Jobs page with its whole reply. Seen here, they're read. A page at a time as the table is scrolled.
  const { client, chats, notices } = useDaemon();
  const notifications = pagedResource(
    (c, page) => c.notifications.list(page),
    (n) => n.id,
    ["notifications"],
  );
  // For the icon of the plugin whose work ended.
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  let picked = $state<string | null>(null);
  let clearing = $state(false);
  // Until one is picked: the newest.
  const shown = $derived(notifications.items.find((n) => n.id === picked) ?? notifications.items[0]);

  onMount(() => {
    client.notifications.markRead().catch((e) => notices.report(e));
  });

  function kind(n: Notification): string {
    return n.kind === "job" ? "Scheduled job" : n.kind === "doctor" ? "Health check" : "Background work";
  }

  function jobLink(n: Notification): string {
    return `${resolve("/jobs")}${runQuery(n.job, n.run_at)}`;
  }

  async function dismiss(n: Notification): Promise<void> {
    try {
      await client.notifications.dismiss(n.id);
    } catch (e) {
      notices.report(e);
    }
  }

  async function clear(): Promise<void> {
    clearing = false;
    try {
      await client.notifications.clear();
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<TopBar title="Notifications">
  {#snippet actions()}
    {#if notifications.items.length}
      <button class="btn btn--ghost" onclick={() => (clearing = true)}
        ><BellOff size={16} /><span class="hide-narrow">Clear all</span></button
      >
    {/if}
  {/snippet}
</TopBar>

<div class="screen">
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">What finished</h2>
        <p class="text-meta">Scheduled jobs' results, background work that ended and health checks. Click one to see it on the right.</p>
      </div>
      {#if notifications.loaded}<span class="pill">{notifications.items.length}{notifications.done ? "" : "+"}</span>{/if}
    </header>
    <div class="scroll">
      {#if notifications.error && !notifications.items.length}
        <p class="error-text pad">{notifications.error}</p>
      {:else if notifications.loaded && !notifications.items.length}
        <EmptyState
          icon={ListChecks}
          title="Nothing yet"
          text="When a scheduled job runs or background work ends (a coding task, a download), it shows up here."
        />
      {:else if shown}
        <table class="data-table">
          <thead><tr><th>About</th><th>What happened</th><th class="hide-narrow">When</th></tr></thead>
          <tbody>
            {#each notifications.items as n (n.id)}
              <tr class:selected={n.id === shown.id} class:failed={!n.ok} onclick={() => (picked = n.id)}>
                <td>
                  <button class="row-button" onclick={() => (picked = n.id)}>
                    {#if n.plugin && installedIcon(servers.data, n.plugin)}<span class="plugin-icon"
                        ><PluginIcon icon={installedIcon(servers.data, n.plugin)} size={16} /></span
                      >{/if}{n.title}
                  </button>
                </td>
                <td class="text-label summary">{n.text}</td>
                <td class="text-label hide-narrow">{localTime(n.at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <ListEnd list={notifications} />
      {/if}
    </div>
  </section>

  <div class="column">
    {#if shown}
      <section class="details surface--glass">
        <header>
          <h2 class="text-heading">{shown.title}</h2>
          <span class="pill" class:pill--danger={!shown.ok}>{shown.ok ? "done" : "needs a look"}</span>
        </header>
        <dl>
          <dt class="micro-label">Kind</dt>
          <dd>{kind(shown)}</dd>
          <dt class="micro-label">When</dt>
          <dd>{localTime(shown.at)}</dd>
        </dl>
        <p class="text">{shown.text}</p>
        <div class="actions">
          <!-- Work started in the inbox has no conversation to open: Chat never shows the inbox. -->
          {#if shown.thread_id && shown.thread_id !== chats.inboxId}
            <button class="btn btn--neutral btn--sm" onclick={() => openConversation(chats, notices, shown.thread_id)}
              >Open its conversation</button
            >
          {:else if shown.job}
            <a class="btn btn--neutral btn--sm" href={jobLink(shown)}>Open the job</a>
          {:else if shown.kind === "doctor"}
            <a class="btn btn--neutral btn--sm" href={resolve("/doctor")}>Open the health check</a>
          {/if}
          <button class="btn btn--ghost btn--sm" onclick={() => dismiss(shown)}>Dismiss</button>
        </div>
      </section>
    {:else}
      <section class="details surface--glass">
        <EmptyState icon={ListChecks} title="No notification selected" text="Job results and finished background work show here." />
      </section>
    {/if}
  </div>
</div>

{#if clearing}
  <Confirm
    title="Clear every notification?"
    text="The jobs and the work they're about aren't touched."
    action="Clear all"
    onanswer={(yes) => (yes ? clear() : (clearing = false))}
  />
{/if}

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  /* The table takes three quarters of the width, the notification the rest. */
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
  tr.failed td:first-child .row-button {
    color: var(--color-danger);
  }
  .summary {
    max-width: 0;
    width: 60%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
  }
  .row-button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .plugin-icon {
    display: inline-flex;
    color: var(--color-text-muted);
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
  .text {
    margin: 0;
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
