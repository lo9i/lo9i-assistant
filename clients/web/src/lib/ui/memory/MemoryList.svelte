<script lang="ts">
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type UserRound from "@lucide/svelte/icons/user-round";
  import { t } from "$lib/i18n.svelte";
  import { matching, type MemoryItem } from "$lib/memory";
  import { pageOf } from "$lib/paging";
  import Confirm from "../Confirm.svelte";
  import Pager from "../Pager.svelte";
  import SearchField from "../SearchField.svelte";

  // Saved facts or past conversations: searched, edited in place and deleted after confirming.
  type Props = {
    title: string;
    noun: string;
    items: MemoryItem[];
    Icon: typeof UserRound;
    onedit: (id: string, text: string) => Promise<void>;
    ondelete: (id: string) => Promise<void>;
  };
  let { title, noun, items, Icon, onedit, ondelete }: Props = $props();
  const PAGE = 15;
  let query = $state("");
  let page = $state(0);
  let editing = $state<string | null>(null);
  let draft = $state("");
  let deleting = $state<MemoryItem | null>(null);
  let busy = $state(false);
  const found = $derived(matching(items, query));

  $effect(() => {
    void query;
    page = 0;
  });

  async function run(change: () => Promise<void>): Promise<void> {
    busy = true;
    try {
      await change();
    } finally {
      busy = false;
    }
  }

  function edit(item: MemoryItem): void {
    editing = item.id;
    draft = item.text;
  }

  async function finishEdit(item: MemoryItem): Promise<void> {
    if (editing !== item.id) return;
    editing = null;
    if (draft.trim() && draft.trim() !== item.text) await run(() => onedit(item.id, draft.trim()));
  }

  function onEditKey(e: KeyboardEvent, item: MemoryItem): void {
    if (e.key === "Enter") void finishEdit(item);
    if (e.key === "Escape") editing = null;
  }

  function answerDelete(yes: boolean): void {
    const item = deleting;
    deleting = null;
    if (yes && item) void run(() => ondelete(item.id));
  }
</script>

<section class="list surface--glass">
  <header>
    <span class="icon"><Icon size={16} /></span>
    <h3 class="micro-label">{title}</h3>
    <span class="pill">{items.length}</span>
    {#if items.length > PAGE}<SearchField bind:value={query} label={t("memory.search", { title: title.toLowerCase() })} />{/if}
  </header>
  {#if !items.length}
    <p class="text-caption">{t("memory.noneYet")}</p>
  {:else if !found.length}
    <p class="text-caption">{t("memory.nothingMatches")}</p>
  {:else}
    <ul>
      {#each pageOf(found, page, PAGE) as item (item.id)}
        <li>
          {#if editing === item.id}
            <!-- svelte-ignore a11y_autofocus -->
            <textarea
              class="input"
              rows="2"
              bind:value={draft}
              onkeydown={(e) => onEditKey(e, item)}
              onblur={() => finishEdit(item)}
              aria-label={t("memory.editNoun", { noun })}
              autofocus></textarea>
          {:else}
            <span class="text">{item.text}<span class="text-caption when">{item.when}</span></span>
            <span class="tools">
              <button class="tool" aria-label={t("common.edit")} title={t("common.edit")} disabled={busy} onclick={() => edit(item)}
                ><Pencil size={14} /></button
              >
              <button
                class="tool"
                aria-label={t("common.delete")}
                title={t("common.delete")}
                disabled={busy}
                onclick={() => (deleting = item)}
              >
                <Trash2 size={14} />
              </button>
            </span>
          {/if}
        </li>
      {/each}
    </ul>
    {#if found.length > PAGE}<Pager bind:page total={found.length} size={PAGE} />{/if}
  {/if}
</section>

{#if deleting}
  <Confirm
    title={t("memory.deleteTitle", { noun })}
    text={t("memory.deleteText", { text: deleting.text })}
    action={t("common.delete")}
    onanswer={answerDelete}
  />
{/if}

<style>
  .list {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }
  .icon {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-brand) 18%, transparent);
    color: var(--color-brand);
  }
  h3 {
    flex: 1;
    margin: 0;
  }
  ul {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    min-height: 32px;
    padding: 6px 4px 6px 10px;
    border-radius: var(--radius-sm);
  }
  li:hover {
    background: var(--color-bg-hover-ghost);
  }
  .text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .tools {
    display: flex;
    gap: 2px;
    opacity: 0;
  }
  li:hover .tools,
  li:focus-within .tools {
    opacity: 1;
  }
  .tool {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .tool:hover {
    color: var(--color-text-primary);
  }
  li textarea {
    flex: 1;
    resize: vertical;
  }
  p {
    margin: 0;
  }
  @media (hover: none) {
    .tools {
      opacity: 1;
    }
  }
</style>
