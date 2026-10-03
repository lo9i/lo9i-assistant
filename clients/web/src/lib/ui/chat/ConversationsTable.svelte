<script lang="ts">
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import type { Conversation } from "$lib/api/types";
  import { duration } from "$lib/duration";
  import EmptyState from "../EmptyState.svelte";
  import SearchField from "../SearchField.svelte";

  type Props = {
    conversations: Conversation[] | undefined;
    error: string | null;
    /** The conversation shown in the preview. */
    selected: string | null;
    /** The conversation this tab is on. */
    current: string;
    onselect: (threadId: string) => void;
  };
  let { conversations, error, selected, current, onselect }: Props = $props();
  let query = $state("");

  const shown = $derived(
    (conversations ?? [])
      .filter((c) => c.title.toLowerCase().includes(query.trim().toLowerCase()))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
  );

  function when(iso: string): string {
    const date = new Date(iso);
    const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (date.toDateString() === new Date().toDateString()) return `Today ${time}`;
    return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
  }
</script>

<section class="table-card surface--glass">
  <header class="toolbar">
    <div>
      <h2 class="text-heading">All conversations</h2>
      <p class="text-meta">Click one to read it on the right.</p>
    </div>
    <SearchField bind:value={query} label="Search conversations" />
  </header>
  <div class="scroll">
    {#if error}
      <p class="error-text pad">{error}</p>
    {:else if conversations?.length === 0}
      <EmptyState icon={MessagesSquare} title="No conversations yet" text="Send a message below to start one." />
    {:else if conversations}
      <table class="data-table">
        <thead><tr><th>Title</th><th>Channel</th><th>Started</th><th>Duration</th></tr></thead>
        <tbody>
          {#each shown as c (c.thread_id)}
            <tr class:selected={c.thread_id === selected} onclick={() => onselect(c.thread_id)}>
              <td>
                <button class="title" onclick={(e) => (e.stopPropagation(), onselect(c.thread_id))}>{c.title || "Untitled"}</button>
                {#if c.thread_id === current}<span class="pill pill--accent">This tab</span>{/if}
              </td>
              <td>
                {#each c.channels ?? [] as channel (channel)}<span class="pill channel">{channel}</span>{:else}<span
                    class="text-caption">—</span
                  >{/each}
              </td>
              <td class="text-label">{when(c.started_at)}</td>
              <td class="text-label">{duration(c.started_at, c.updated_at)}</td>
            </tr>
          {:else}
            <tr><td colspan="4" class="text-meta">No matches.</td></tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>
</section>

<style>
  .table-card {
    display: flex;
    flex-direction: column;
    min-height: 0;
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
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
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
  .title {
    border: 0;
    background: none;
    padding: 0;
    margin-right: 8px;
    font-weight: 500;
    cursor: pointer;
  }
  .pad {
    padding: 24px;
  }
  .channel {
    margin-right: 4px;
    font-weight: 500;
  }
</style>
