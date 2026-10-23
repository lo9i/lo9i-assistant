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
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 16px;
    min-height: 28px;
    padding: 0 16px 6px 24px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
</style>
