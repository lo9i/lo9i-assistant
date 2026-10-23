<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import type { Handoff } from "$lib/api/types";

  // In the status bar: the agent this conversation is handed to (/claude), whose replies come from it, not the
  // assistant. While it works, Interrupt stops its step in progress and it waits for the user's next message.
  type Props = { handoff: Handoff; working?: boolean; oninterrupt?: () => void; onback: () => void };
  let { handoff, working = false, oninterrupt, onback }: Props = $props();
</script>

<div class="agent">
  <Bot size={13} aria-hidden="true" />
  <span>Talking to <strong>{handoff.name}</strong> in <code>{handoff.folder}</code></span>
  {#if working && oninterrupt}
    <button type="button" class="btn btn--ghost btn--sm" title="Stop its current step and wait for you" onclick={oninterrupt}>
      Interrupt
    </button>
  {/if}
  <button type="button" class="btn btn--ghost btn--sm" onclick={onback}>Back to the assistant</button>
</div>

<style>
  .agent {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    min-width: 0;
  }
  .agent span {
    min-width: 0;
    overflow-wrap: anywhere;
  }
</style>
