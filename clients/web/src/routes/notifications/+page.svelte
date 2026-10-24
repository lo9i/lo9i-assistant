<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import BellOff from "@lucide/svelte/icons/bell-off";
  import ListChecks from "@lucide/svelte/icons/list-checks";
  import type { Notification } from "$lib/api/types";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { localTime } from "$lib/health";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  // Scheduled jobs' results and background work that ended (core/notifications.py), apart from any
  // conversation. Each opens the conversation its work was started in, when it has one, and a job's run opens on
  // the Jobs page with its whole reply. Seen here, they're read.
  const { client, chats, notices } = useDaemon();
  const notifications = resource((c) => c.notifications.list(), ["notifications"]);
  let picked = $state<string | null>(null);
  let clearing = $state(false);
  // Until one is picked: the newest.
  const shown = $derived(notifications.data?.find((n) => n.id === picked) ?? notifications.data?.[0]);

  onMount(() => {
    client.notifications.markRead().catch((e) => notices.report(e));
  });

  function kind(n: Notification): string {
    return n.kind === "job" ? "Scheduled job" : "Background work";
  }

  async function openConversation(n: Notification): Promise<void> {
    try {
      await chats.show(n.thread_id);
      await goto(resolve("/conversations/open"));
    } catch (e) {
      notices.report(e);
    }
  }

  function jobLink(n: Notification): string {
    return `${resolve("/jobs")}?job=${encodeURIComponent(n.job)}&run=${encodeURIComponent(n.run_at)}`;
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
    {#if notifications.data?.length}
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
        <p class="text-meta">Scheduled jobs' results and background work that ended. Click one to see it on the right.</p>
      </div>
      {#if notifications.data}<span class="pill">{notifications.data.length}</span>{/if}
    </header>
    <div class="scroll">
      {#if notifications.error}
        <p class="error-text pad">{notifications.error}</p>
      {:else if notifications.data?.length === 0}
        <EmptyState
          icon={ListChecks}
          title="Nothing yet"
          text="When a scheduled job runs or background work ends (a coding task, a download), it shows up here."
        />
      {:else if notifications.data && shown}
        <table class="data-table">
          <thead><tr><th>About</th><th>What happened</th><th class="hide-narrow">When</th></tr></thead>
          <tbody>
            {#each notifications.data as n (n.id)}
              <tr class:selected={n.id === shown.id} class:failed={!n.ok} onclick={() => (picked = n.id)}>
                <td><button class="row-button" onclick={() => (picked = n.id)}>{n.title}</button></td>
                <td class="text-label summary">{n.text}</td>
                <td class="text-label hide-narrow">{localTime(n.at)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
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
          {#if shown.thread_id}
            <button class="btn btn--neutral btn--sm" onclick={() => openConversation(shown)}>Open its conversation</button>
          {:else if shown.job}
            <a class="btn btn--neutral btn--sm" href={jobLink(shown)}>Open the job</a>
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
    padding: 0 16px 16px;
    height: calc(100dvh - 76px);
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
