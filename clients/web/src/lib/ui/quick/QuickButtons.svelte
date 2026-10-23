<script lang="ts">
  import TextButton from "./TextButton.svelte";
  import VoiceButton from "./VoiceButton.svelte";
  import { quickDock } from "./openPanel.svelte";

  // The quick text and voice buttons, 10px from the window's bottom right corner: typing above talking, or
  // `docked` in a row while a chat is shown, beside its status bar (AppShell doesn't show its own then).
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
    right: 10px;
    bottom: 10px;
    z-index: var(--z-popover);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .docked {
    flex-direction: row;
  }
</style>
