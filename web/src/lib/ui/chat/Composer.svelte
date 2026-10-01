<script lang="ts">
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Square from "@lucide/svelte/icons/square";
  import X from "@lucide/svelte/icons/x";
  import { offered, parse, takesArgument, type Command } from "$lib/chat/commands";
  import { pastedFiles } from "$lib/chat/pasted";

  type Props = {
    busy: boolean;
    running: boolean;
    onsend: (text: string, files: File[]) => void;
    onstop: () => void;
    /** A slash command other than /attach, which the composer handles itself. */
    oncommand: (name: string, arg: string) => void;
    /** Lets the page put text in the box, such as a suggested prompt. */
    text?: string;
  };
  let { busy, running, onsend, onstop, oncommand, text = $bindable("") }: Props = $props();

  let files = $state<File[]>([]);
  let highlight = $state(0);
  let picker = $state<HTMLInputElement>();
  let box = $state<HTMLTextAreaElement>();
  const menu = $derived(offered(text));
  const chosen = $derived(menu[Math.min(highlight, menu.length - 1)]);
  const previews = $derived(files.map((file) => (file.type.startsWith("image/") ? URL.createObjectURL(file) : null)));

  $effect(() => () => previews.forEach((url) => url && URL.revokeObjectURL(url)));

  function type(value: string): void {
    text = value;
    highlight = 0;
  }

  function run(name: string, arg: string): void {
    type("");
    if (name === "/attach") picker?.click();
    else oncommand(name, arg);
  }

  /** Fills in the command, or runs it when it needs nothing more. */
  function pick(command: Command): void {
    if (takesArgument(command)) type(command.name + " ");
    else run(command.name, "");
    box?.focus();
  }

  function submit(): void {
    const command = parse(text);
    if (command !== null) {
      if (chosen && chosen.name !== command.name) pick(chosen);
      else run(command.name, command.arg);
      return;
    }
    if (busy || (!text.trim() && files.length === 0)) return;
    onsend(text.trim(), files);
    type("");
    files = [];
  }

  /** Up, Down, Tab and Esc while the command menu is open. */
  function menuKey(e: KeyboardEvent): boolean {
    const moves: Record<string, number> = { ArrowUp: -1, ArrowDown: 1 };
    if (e.key in moves) highlight = (highlight + moves[e.key] + menu.length) % menu.length;
    else if (e.key === "Tab" && chosen) type(chosen.name + (takesArgument(chosen) ? " " : ""));
    else if (e.key === "Escape") type("");
    else return false;
    e.preventDefault();
    return true;
  }

  function onkeydown(e: KeyboardEvent): void {
    if (menu.length && menuKey(e)) return;
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape" && running) {
      onstop();
    }
  }

  function onpaste(e: ClipboardEvent): void {
    const pasted = e.clipboardData ? pastedFiles(e.clipboardData) : [];
    if (pasted.length === 0) return;
    e.preventDefault();
    files = [...files, ...pasted];
  }
</script>

<div class="dock">
  {#if menu.length}
    <ul class="menu" role="listbox" aria-label="Commands">
      {#each menu as command (command.name)}
        <li
          role="option"
          aria-selected={command === chosen}
          class:active={command === chosen}
          onmousedown={(e) => {
            e.preventDefault();
            pick(command);
          }}
        >
          <code>{command.usage}</code>
          <span class="text-caption">{command.description}</span>
        </li>
      {/each}
    </ul>
  {/if}
  {#if files.length}
    <div class="attachments">
      {#each files as file, i (i)}
        <div class="chip">
          {#if previews[i]}<img src={previews[i]} alt="" />{:else}<span class="doc"><Paperclip size={14} /></span>{/if}
          <span class="chip-name">{file.name}</span>
          <button aria-label="Remove {file.name}" onclick={() => (files = files.filter((_, j) => j !== i))}>
            <X size={12} />
          </button>
        </div>
      {/each}
    </div>
  {/if}
  <div class="composer" class:multiline={text.includes("\n") || text.length > 80}>
    <button class="lead" aria-label="Attach files" title="Attach files" onclick={() => picker?.click()}>
      <Paperclip size={16} />
    </button>
    <input
      bind:this={picker}
      type="file"
      multiple
      hidden
      onchange={(e) => {
        files = [...files, ...Array.from(e.currentTarget.files ?? [])];
        e.currentTarget.value = "";
      }}
    />
    <!-- svelte-ignore a11y_autofocus -->
    <textarea
      bind:this={box}
      value={text}
      placeholder="Message, or / for commands"
      rows={1}
      oninput={(e) => type(e.currentTarget.value)}
      {onkeydown}
      {onpaste}
      autofocus
    ></textarea>
    {#if running}
      <button class="send" aria-label="Stop" title="Stop (Esc)" onclick={onstop}><Square size={12} fill="currentColor" /></button>
    {:else}
      <button class="send" aria-label="Send" onclick={submit} disabled={!text.trim() && files.length === 0}>
        <ArrowUp size={14} />
      </button>
    {/if}
  </div>
  <p class="text-caption hint">Enter to send · Shift+Enter for a new line · / for commands</p>
</div>

<style>
  .dock {
    position: relative;
    padding: 8px 16px 12px;
  }
  .composer {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 10px 8px 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    background: var(--color-bg-hover-ghost);
    transition: border-color 0.12s ease;
  }
  .composer.multiline {
    border-radius: 16px;
    align-items: flex-end;
  }
  .composer:focus-within {
    border-color: var(--color-accent);
  }
  .lead {
    display: grid;
    place-items: center;
    flex: none;
    width: 30px;
    height: 30px;
    border: 0;
    border-radius: 50%;
    background: none;
    color: var(--color-text-faint);
    cursor: pointer;
  }
  .lead:hover {
    color: var(--color-text-primary);
  }
  textarea {
    flex: 1;
    border: 0;
    outline: none;
    resize: none;
    background: transparent;
    font-size: 0.92rem;
    line-height: 1.4;
    padding: 8px 4px;
    max-height: 140px;
    field-sizing: content;
  }
  textarea::placeholder {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .send {
    display: grid;
    place-items: center;
    flex: none;
    width: 34px;
    height: 34px;
    border: 0;
    border-radius: 50%;
    background: var(--color-action-primary);
    color: var(--color-action-on-primary);
    cursor: pointer;
    transition: transform 0.12s ease;
  }
  .send:hover:not(:disabled) {
    transform: scale(1.05);
  }
  .send:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .hint {
    text-align: center;
    margin: 8px 0 0;
  }
  .menu {
    position: absolute;
    left: 16px;
    right: 16px;
    bottom: calc(100% - 4px);
    z-index: var(--z-popover);
    list-style: none;
    margin: 0;
    padding: 4px;
    max-height: min(50vh, 420px);
    overflow-y: auto;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-md);
    background: var(--surface-modal-bg);
    backdrop-filter: var(--surface-glass-blur);
    box-shadow: var(--shadow-popover);
  }
  .menu li {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
    cursor: pointer;
  }
  .menu li.active {
    background: var(--color-bg-hover-ghost);
  }
  .menu code {
    min-width: 140px;
    font-size: var(--font-size-sm);
  }
  .attachments {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }
  .chip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px 4px 4px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-bg-hover-ghost);
  }
  .chip img,
  .doc {
    width: 38px;
    height: 38px;
    border-radius: var(--radius-sm);
    object-fit: cover;
  }
  .doc {
    display: grid;
    place-items: center;
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-muted);
  }
  .chip-name {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--font-size-xs);
    font-weight: 500;
  }
  .chip button {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border: 0;
    border-radius: 50%;
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-muted);
    cursor: pointer;
  }
</style>
