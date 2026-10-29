<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import type { Snippet } from "svelte";
  import type { Handoff } from "$lib/api/types";

  // In the status bar: the agent this conversation is handed to (/claude), whose replies come from it, not the
  // assistant. Named where the assistant's model is otherwise, so it's plain who answers. `children` (its context)
  // goes between its name and the way back. Its name turns Claude's orange while it works on a message.
  type Props = { handoff: Handoff; working?: boolean; onback: () => void; children?: Snippet };
  let { handoff, working = false, onback, children }: Props = $props();
</script>

<div class="agent" title="{handoff.name} in {handoff.folder}">
  <Bot size={13} aria-hidden="true" />
  <span class="name" class:working>{handoff.name}</span>
  {@render children?.()}
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
  .name {
    cursor: default;
    color: #e5b931;
    transition: color 0.2s ease;
  }
  .name.working {
    color: #e68d77;
  }
</style>
