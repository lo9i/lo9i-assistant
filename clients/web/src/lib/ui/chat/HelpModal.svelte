<script lang="ts">
  import { COMMANDS, type Command } from "$lib/chat/commands";
  import Modal from "../Modal.svelte";

  // `extra`: the commands installed plugins add, such as /claude.
  let { onclose, extra = [] }: { onclose: () => void; extra?: Command[] } = $props();

  const KEYS = [
    ["Enter", "Send"],
    ["Shift+Enter", "New line"],
    ["↑ / ↓", "Your earlier messages in this conversation"],
    ["Esc", "Stop the reply"],
    ["Tab", "Complete a command"],
    ["⌘B", "Collapse the sidebar"],
    ["Paste", "Attach a copied screenshot or image"],
  ];
</script>

<Modal title="Commands and keys" width={580} {onclose}>
  <table class="help">
    <tbody>
      {#each [...COMMANDS, ...extra] as c (c.name)}
        <tr><td><code>{c.usage}</code></td><td>{c.description}</td></tr>
      {/each}
      {#each KEYS as [key, what] (key)}
        <tr><td><kbd>{key}</kbd></td><td>{what}</td></tr>
      {/each}
    </tbody>
  </table>
</Modal>

<style>
  .help td {
    padding: 5px 16px 5px 0;
    vertical-align: top;
  }
  .help td:last-child {
    color: var(--color-text-muted);
  }
</style>
