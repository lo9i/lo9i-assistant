<script lang="ts">
  import type { Snippet } from "svelte";

  // A line under the message box with the conversation's state, such as the agent it's handed to. Always there,
  // so the box doesn't move when an item comes or goes; and one line however narrow the chat gets (a side panel
  // open beside it): items with text to spare (the conversation's figures) are cut short instead. Only where even the
  // controls don't fit, on a phone or a conversation sharing the page with others, it wraps: it goes by its own width,
  // not the window's.
  let { children }: { children?: Snippet } = $props();
</script>

<div class="room">
  <footer class="status-bar" role="status">
    {@render children?.()}
  </footer>
</div>

<style>
  .room {
    container: status-bar / inline-size;
  }
  .status-bar {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    gap: 4px 16px;
    min-height: 28px;
    padding: 0 16px 6px 24px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    white-space: nowrap;
  }
  @container status-bar (max-width: 640px) {
    .status-bar {
      flex-wrap: wrap;
      gap: 4px 10px;
      white-space: normal;
    }
  }
</style>
