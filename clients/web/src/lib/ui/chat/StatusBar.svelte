<script lang="ts">
  import type { Snippet } from "svelte";

  // A line under the message box with the conversation's state, such as the agent it's handed to. Always there,
  // so the box doesn't move when an item comes or goes.
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
    /* Room on the right for the voice button floating in the window's corner, as the box above has. */
    padding: 0 48px 6px 24px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
</style>
