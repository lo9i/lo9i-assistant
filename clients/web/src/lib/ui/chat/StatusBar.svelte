<script lang="ts">
  import type { Snippet } from "svelte";

  // A line under the message box with the conversation's state, such as the agent it's handed to, and the quick
  // text and voice buttons at its right end. Always there, so the box doesn't move when an item comes or goes.
  let { children }: { children?: Snippet } = $props();
</script>

<footer class="status-bar" role="status">
  {@render children?.()}
</footer>

<style>
  .status-bar {
    /* Read by the quick buttons, which sit closer to the chat's corner than the padding. */
    --status-bar-right: 16px;
    --status-bar-bottom: 6px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 16px;
    min-height: 28px;
    padding: 0 var(--status-bar-right) var(--status-bar-bottom) 24px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
</style>
