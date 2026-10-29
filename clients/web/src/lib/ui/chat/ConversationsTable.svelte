<script lang="ts">
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import Play from "@lucide/svelte/icons/play";
  import type { Conversation } from "$lib/api/types";
  import { newestFirst } from "$lib/chat/order";
  import { matching, messageSearch } from "$lib/chat/search";
  import { resource } from "$lib/daemon.svelte";
  import { duration } from "$lib/duration";
  import EmptyState from "../EmptyState.svelte";
  import SearchField from "../SearchField.svelte";

  type Props = {
    conversations: Conversation[] | undefined;
    error: string | null;
    /** The conversation shown in the preview. */
    selected: string | null;
    /** The conversation this tab is on. */
    // The conversations open in this tab.
    open: string[];
    onselect: (threadId: string) => void;
    /** Continue the conversation in the chat: double-click a row, or its continue button. */
    oncontinue: (threadId: string) => void;
  };
  let { conversations, error, selected, open, onselect, oncontinue }: Props = $props();
  let query = $state("");
  // Titles match as it's typed; the daemon searches what was said once typing pauses.
  let searched = $state("");
  $effect(() => {
    const words = messageSearch(query);
    const timer = setTimeout(() => (searched = words), 250);
    return () => clearTimeout(timer);
  });
  const containing = resource((c) => (searched ? c.conversations.containing(searched) : Promise.resolve([])), ["conversations"]);

  const shown = $derived(matching(conversations ?? [], query, containing.data ?? []).sort(newestFirst));

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
      <h2 class="text-heading">Conversations</h2>
      <p class="text-meta">Newest first. Click one to read it on the right; double-click to continue it.</p>
    </div>
    <SearchField bind:value={query} label="Search conversations" />
  </header>
  {#if containing.error}<p class="error-text pad">Couldn't search what was said: {containing.error}</p>{/if}
  <div class="scroll">
    {#if error}
      <p class="error-text pad">{error}</p>
    {:else if conversations?.length === 0}
      <EmptyState
        icon={MessagesSquare}
        title="No conversations yet"
        text="Write a message above: it starts one, or goes on in the one it's about."
      />
    {:else if conversations}
      <table class="data-table">
        <thead>
          <tr>
            <th>Title</th><th>Channel</th><th>Started</th><th>Duration</th><th class="continue" aria-label="Continue"></th>
          </tr>
        </thead>
        <tbody>
          {#each shown as c (c.thread_id)}
            <tr class:selected={c.thread_id === selected} onclick={() => onselect(c.thread_id)} ondblclick={() => oncontinue(c.thread_id)}>
              <td>
                <button class="title" onclick={(e) => (e.stopPropagation(), onselect(c.thread_id))}>{c.title || "Untitled"}</button>
                {#if c.archived}<span class="pill" title="Kept to read; new messages aren't routed to it">Archived</span>{/if}
                {#if open.includes(c.thread_id)}<span class="pill pill--accent">Open</span>{/if}
                {#if c.tags?.length}<p class="tags text-caption">{c.tags.join(" · ")}</p>{/if}
              </td>
              <td>
                {#each c.channels ?? [] as channel (channel)}<span class="pill channel">{channel}</span>{:else}<span class="text-caption"
                    >—</span
                  >{/each}
              </td>
              <td class="text-label">{when(c.started_at)}</td>
              <td class="text-label">{duration(c.started_at, c.updated_at)}</td>
              <td class="continue">
                <button
                  class="btn btn--icon"
                  aria-label="Continue this conversation"
                  title="Continue this conversation"
                  onclick={(e) => (e.stopPropagation(), oncontinue(c.thread_id))}
                >
                  <Play size={16} />
                </button>
              </td>
            </tr>
          {:else}
            <tr><td colspan="5" class="text-meta">No matches.</td></tr>
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
  .tags {
    margin: 2px 0 0;
  }
  .pad {
    padding: 24px;
  }
  .continue {
    width: 1%;
    text-align: right;
  }
  .channel {
    margin-right: 4px;
    font-weight: 500;
  }
</style>
