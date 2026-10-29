<script lang="ts">
  import { COMMANDS, commandText, type Command } from "$lib/chat/commands";
  import { t, type Key } from "$lib/i18n.svelte";
  import Modal from "../Modal.svelte";

  // `extra`: the commands installed plugins add, such as /claude.
  let { onclose, extra = [] }: { onclose: () => void; extra?: Command[] } = $props();

  const KEYS: Array<[string, Key]> = [
    ["Enter", "help.send"],
    ["Shift+Enter", "help.newLine"],
    ["↑ / ↓", "help.earlier"],
    ["Esc", "help.stop"],
    ["Tab", "help.complete"],
    ["⌘B", "help.collapse"],
    ["Paste", "help.paste"],
  ];
</script>

<Modal title={t("help.title")} width={580} {onclose}>
  <table class="help">
    <tbody>
      {#each [...COMMANDS, ...extra] as c (c.name)}
        <tr><td><code>{c.usage}</code></td><td>{commandText(c)}</td></tr>
      {/each}
      {#each KEYS as [key, what] (key)}
        <tr><td><kbd>{key === "Paste" ? t("help.pasteKey") : key}</kbd></td><td>{t(what)}</td></tr>
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
