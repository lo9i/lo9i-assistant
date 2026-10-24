<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how full the conversation's context is. At the limit, older messages are summarized. While
  // the conversation is handed to an agent (/claude), the agent's context, as of its last answer.
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished", "handoffs"]);
  const shown = $derived(
    stats.data && !stats.error && stats.data.thread_id === threadId && stats.data.context_limit > 0 && stats.data.context_tokens > 0
      ? stats.data
      : null,
  );
  const ratio = $derived(shown ? Math.min(1, shown.context_tokens / shown.context_limit) : 0);
  const SEGMENTS = 24;
  const filled = $derived(Math.round(ratio * SEGMENTS));
  const color = $derived(ratio > 0.9 ? "#e5534b" : ratio > 0.7 ? "#e5b931" : "var(--color-accent)");
  const title = $derived.by(() => {
    if (!shown) return "";
    const figures = `${compact(shown.context_tokens)} / ${compact(shown.context_limit)} tokens (${Math.round(ratio * 100)}%)`;
    return shown.context_agent
      ? `${shown.context_agent}'s context: ${figures}, as of its last answer. It compacts older messages as it nears full.`
      : `Context: ${figures}. Older messages are summarized when it's full.`;
  });
</script>

{#if shown}
  <span class="fuel" {title}>
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
    height: 10px;
    transform: translateY(-1px);
    cursor: default;
  }
  .seg {
    width: 3px;
    height: 100%;
    border-radius: 2px;
  }
</style>
