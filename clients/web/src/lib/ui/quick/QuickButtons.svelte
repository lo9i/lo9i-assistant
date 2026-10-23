<script lang="ts">
  import TextButton from "./TextButton.svelte";
  import VoiceButton from "./VoiceButton.svelte";
  import { quickDock } from "./openPanel.svelte";

  // The quick text and voice buttons. Floating in the window's bottom right corner, typing above talking; or
  // `docked` in a row in a chat's status bar, while which they don't float (AppShell).
  let { docked = false }: { docked?: boolean } = $props();

  $effect(() => {
    if (!docked) return;
    quickDock.count++;
    return () => quickDock.count--;
  });
</script>

<div class="quick" class:docked>
  <TextButton {docked} />
  <VoiceButton {docked} />
</div>

<style>
  .quick {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  /* 5px from the chat's bottom right corner, past the status bar's padding. */
  .docked {
    position: static;
    flex-direction: row;
    align-self: flex-end;
    margin: 0 calc(5px - var(--status-bar-right, 0px)) calc(5px - var(--status-bar-bottom, 0px)) auto;
  }
</style>
