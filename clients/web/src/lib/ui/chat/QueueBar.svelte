<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import Check from "@lucide/svelte/icons/check";
  import Clock from "@lucide/svelte/icons/clock";
  import Paperclip from "@lucide/svelte/icons/paperclip";
  import Pencil from "@lucide/svelte/icons/pencil";
  import X from "@lucide/svelte/icons/x";
  import { t } from "$lib/i18n.svelte";
  import type { QueueEntry } from "$lib/chat/queue";

  // The messages waiting to be read, above the message box while there's one: each can be changed in place or taken
  // out of the queue, until it's read and shows in the chat instead. With several, the list folds away.
  type Props = {
    entries: QueueEntry[];
    onedit: (entry: QueueEntry, text: string) => Promise<void>;
    onremove: (entry: QueueEntry) => Promise<void>;
  };
  let { entries, onedit, onremove }: Props = $props();

  let folded = $state(false);
  // The message being changed, by its key, and what it says so far.
  let editing = $state<string | null>(null);
  let draft = $state("");
  // The messages whose change or removal the daemon is still answering.
  let answering = $state<string[]>([]);
  // Read meanwhile (the agent got to it), it isn't being changed any more.
  const edited = $derived(entries.find((e) => e.key === editing) ?? null);

  function edit(entry: QueueEntry): void {
    editing = entry.key;
    draft = entry.text;
  }

  async function save(entry: QueueEntry): Promise<void> {
    const text = draft.trim();
    if (!text) return;
    editing = null;
    if (text !== entry.text.trim()) await answer(entry, () => onedit(entry, text));
  }

  async function answer(entry: QueueEntry, act: () => Promise<void>): Promise<void> {
    answering = [...answering, entry.key];
    try {
      await act();
    } finally {
      answering = answering.filter((key) => key !== entry.key);
    }
  }

  function keydown(e: KeyboardEvent, entry: QueueEntry): void {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      void save(entry);
    } else if (e.key === "Escape") {
      e.preventDefault();
      editing = null;
    }
  }

  function focus(node: HTMLTextAreaElement): void {
    node.focus();
    node.setSelectionRange(node.value.length, node.value.length);
  }
</script>

{#if entries.length}
  <section class="queue" aria-label={t("chat.queued")}>
    <header>
      <Clock size={13} aria-hidden="true" />
      <span class="count">{t("queue.count", { count: entries.length })}</span>
      {#if entries.length > 1}
        <button
          type="button"
          class="fold"
          class:folded
          aria-expanded={!folded}
          aria-label={folded ? t("queue.show") : t("queue.hide")}
          title={folded ? t("queue.show") : t("queue.hide")}
          onclick={() => (folded = !folded)}
        >
          <ChevronDown size={14} />
        </button>
      {/if}
    </header>
    {#if !folded || entries.length === 1}
      <ul>
        {#each entries as entry (entry.key)}
          {@const busy = answering.includes(entry.key)}
          <li class:busy title={entry.fixed ? t("queue.sentOn") : undefined}>
            {#if edited?.key === entry.key}
              <textarea rows="1" aria-label={t("queue.editing")} bind:value={draft} onkeydown={(e) => keydown(e, entry)} use:focus
              ></textarea>
              <button
                type="button"
                class="act"
                aria-label={t("queue.save")}
                title={t("queue.save")}
                disabled={!draft.trim()}
                onclick={() => save(entry)}
              >
                <Check size={14} />
              </button>
              <button type="button" class="act" aria-label={t("common.cancel")} title={t("common.cancel")} onclick={() => (editing = null)}>
                <X size={14} />
              </button>
            {:else}
              <span class="text" title={entry.fixed ? undefined : entry.text}>{entry.text}</span>
              {#if entry.files.length}
                <span class="files" title={entry.files.join(", ")}>
                  <Paperclip size={11} aria-hidden="true" />{t("queue.files", { count: entry.files.length })}
                </span>
              {/if}
              {#if !entry.fixed}
                <button
                  type="button"
                  class="act"
                  aria-label={t("queue.edit")}
                  title={t("queue.edit")}
                  disabled={busy || !entry.text}
                  onclick={() => edit(entry)}
                >
                  <Pencil size={13} />
                </button>
                <button
                  type="button"
                  class="act remove"
                  aria-label={t("queue.remove")}
                  title={t("queue.remove")}
                  disabled={busy}
                  onclick={() => answer(entry, () => onremove(entry))}
                >
                  <X size={14} />
                </button>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  /* Lined up on the right, as the user's own messages are, with no box around them. */
  .queue {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    margin: 0 16px 6px;
    color: var(--color-text-muted);
    font-size: var(--font-size-sm);
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--color-text-faint);
    font-size: var(--font-size-xs);
    font-weight: 600;
  }
  .count {
    font-variant-numeric: tabular-nums;
  }
  .fold {
    display: grid;
    place-items: center;
    padding: 2px;
    border: 0;
    border-radius: 6px;
    background: none;
    color: inherit;
    cursor: pointer;
    transition: transform 0.15s ease;
  }
  .fold.folded {
    transform: rotate(90deg);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
    width: 100%;
    max-height: 30vh;
    overflow-y: auto;
  }
  /* A user's message waiting: the shape of the bubble they're shown in, only outlined in dashes, not sent yet. */
  li {
    display: flex;
    align-items: center;
    gap: 4px;
    max-width: 70%;
    min-height: 32px;
    padding: 2px 4px 2px 14px;
    border: 1px dashed var(--color-border);
    border-radius: 16px;
    border-bottom-right-radius: 8px;
  }
  li:has(textarea) {
    width: 70%;
  }
  li.busy {
    opacity: 0.55;
  }
  .text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--color-text-primary);
  }
  .files {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    flex: none;
    color: var(--color-text-faint);
    font-size: var(--font-size-xs);
  }
  textarea {
    flex: 1;
    min-width: 0;
    field-sizing: content;
    max-height: 8lh;
    margin: 3px 0;
    padding: 4px 8px;
    border: 1px solid color-mix(in srgb, var(--glow) 70%, transparent);
    border-radius: 8px;
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
    font: inherit;
    resize: none;
    outline: none;
  }
  .act {
    display: grid;
    place-items: center;
    flex: none;
    width: 24px;
    height: 24px;
    border: 0;
    border-radius: 6px;
    background: none;
    color: var(--color-text-faint);
    cursor: pointer;
  }
  .act:hover:not(:disabled) {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .act.remove:hover:not(:disabled) {
    color: var(--color-danger);
  }
  .act:disabled {
    cursor: default;
    opacity: 0.4;
  }
</style>
