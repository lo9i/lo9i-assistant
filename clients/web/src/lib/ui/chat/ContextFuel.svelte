<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how full the conversation's context is. At the limit, older messages are summarized.
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished"]);
  const shown = $derived(
    stats.data && !stats.error && stats.data.thread_id === threadId && stats.data.context_limit > 0 && stats.data.context_tokens > 0
      ? stats.data
      : null,
  );
  const ratio = $derived(shown ? Math.min(1, shown.context_tokens / shown.context_limit) : 0);
  const SEGMENTS = 24;
  const filled = $derived(Math.round(ratio * SEGMENTS));
  const color = $derived(ratio > 0.9 ? "#e5534b" : ratio > 0.7 ? "#e5b931" : "var(--color-accent)");
</script>

{#if shown}
  <span
    class="fuel"
    title="Context: {compact(shown.context_tokens)} / {compact(shown.context_limit)} tokens ({Math.round(ratio * 100)}%). Older messages are summarized when it's full."
  >
    {#each Array(SEGMENTS) as _, i (i)}
      <span class="seg" style="background: {color}; opacity: {i < filled ? 1 : 0.25}"></span>
    {/each}
  </span>
{/if}

<style>
  .fuel {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 12px;
    vertical-align: middle;
    cursor: default;
  }
  .seg {
    width: 3px;
    height: 100%;
    border-radius: 2px;
  }
</style>
