<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import type { Handoff } from "$lib/api/types";

  // The agent this conversation is handed to (/claude): its replies come from it, not the assistant.
  let { handoff, onback }: { handoff: Handoff; onback: () => void } = $props();
</script>

<div class="agent" role="status">
  <Bot size={14} aria-hidden="true" />
  <span>Talking to <strong>{handoff.name}</strong> in <code>{handoff.folder}</code></span>
  <button type="button" class="btn btn--ghost btn--sm" onclick={onback}>Back to the assistant</button>
</div>

<style>
  .agent {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 4px 16px;
    color: var(--color-text-muted);
    font-size: var(--font-size-sm);
  }
  .agent span {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
</style>
