<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import type { Handoff } from "$lib/api/types";

  // In the status bar: the agent this conversation is handed to (/claude), whose replies come from it, not the
  // assistant.
  type Props = { handoff: Handoff; onback: () => void };
  let { handoff, onback }: Props = $props();
</script>

<div class="agent">
  <Bot size={13} aria-hidden="true" />
  <span>Talking to <strong>{handoff.name}</strong> in <code>{handoff.folder}</code></span>
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
