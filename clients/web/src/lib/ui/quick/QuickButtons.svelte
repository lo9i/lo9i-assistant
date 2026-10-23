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
  .docked {
    position: static;
    flex-direction: row;
    margin-left: auto;
  }
</style>
