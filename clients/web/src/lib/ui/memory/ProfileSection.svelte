<script lang="ts">
  import GripVertical from "@lucide/svelte/icons/grip-vertical";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Plus from "@lucide/svelte/icons/plus";
  import X from "@lucide/svelte/icons/x";
  import type UserRound from "@lucide/svelte/icons/user-round";
  import { t } from "$lib/i18n.svelte";
  import { sectionLabel } from "$lib/memory";

  // As in core/memory/profile.py: every item is in every system prompt, so a section stays short.
  const MAX_ITEMS = 8;

  type Props = {
    name: string;
    items: string[];
    Icon: typeof UserRound;
    onsave: (items: string[]) => Promise<void>;
    /** Pressing its handle starts dragging it (mouse, touch or pen); its arrow keys move it one place. */
    ongrab?: (e: PointerEvent) => void;
    onstep?: (by: -1 | 1) => void;
    /** It's the one being dragged. */
    lifted?: boolean;
    /** Where a section dragged over it would go: before it, after it, or nowhere. */
    drop?: "before" | "after" | null;
  };
  let { name, items, Icon, onsave, ongrab, onstep, lifted = false, drop = null }: Props = $props();
  let adding = $state("");
  let editing = $state<number | null>(null);
  let draft = $state("");
  let busy = $state(false);

  async function save(next: string[]): Promise<void> {
    busy = true;
    try {
      await onsave(next);
    } finally {
      busy = false;
    }
  }

  async function add(): Promise<void> {
    if (!adding.trim()) return;
    await save([...items, adding.trim()]);
    adding = "";
  }

  function edit(i: number): void {
    editing = i;
    draft = items[i];
  }

  async function finishEdit(): Promise<void> {
    if (editing === null) return;
    const i = editing;
    editing = null;
    if (draft.trim() !== items[i]) await save(items.map((item, j) => (j === i ? draft : item)));
  }

  function onGripKey(e: KeyboardEvent): void {
    const by = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : 0;
    if (!by || !onstep) return;
    e.preventDefault();
    onstep(by);
  }

  function onEditKey(e: KeyboardEvent): void {
    if (e.key === "Enter") void finishEdit();
    if (e.key === "Escape") editing = null;
  }
</script>

<section
  class="section surface--glass"
  class:lifted
  class:drop-before={drop === "before"}
  class:drop-after={drop === "after"}
  data-section={name}
>
  <header>
    {#if ongrab}
      <button
        class="grip"
        title={t("memory.dragToMove")}
        aria-label={t("memory.moveSection", { section: sectionLabel(name) })}
        onpointerdown={ongrab}
        onkeydown={onGripKey}><GripVertical size={14} /></button
      >
    {/if}
    <span class="icon"><Icon size={16} /></span>
    <h3 class="micro-label">{sectionLabel(name)}</h3>
    <span class="pill">{items.length}/{MAX_ITEMS}</span>
  </header>
  {#if items.length}
    <ul>
      {#each items as item, i (i)}
        <li>
          {#if editing === i}
            <!-- svelte-ignore a11y_autofocus -->
            <input class="input" bind:value={draft} onkeydown={onEditKey} onblur={finishEdit} aria-label={t("memory.editItem")} autofocus />
          {:else}
            <span class="text">{item}</span>
            <span class="tools">
              <button class="tool" aria-label={t("common.edit")} title={t("common.edit")} disabled={busy} onclick={() => edit(i)}
                ><Pencil size={14} /></button
              >
              <button
                class="tool"
                aria-label={t("common.remove")}
                title={t("common.remove")}
                disabled={busy}
                onclick={() => save(items.filter((_, j) => j !== i))}
              >
                <X size={14} />
              </button>
            </span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if items.length < MAX_ITEMS}
    <form
      class="add"
      onsubmit={(e) => {
        e.preventDefault();
        void add();
      }}
    >
      <input
        class="input"
        bind:value={adding}
        placeholder={t("memory.addTo", { section: sectionLabel(name).toLowerCase() })}
        aria-label={t("memory.addTo", { section: sectionLabel(name) })}
      />
      <button class="btn btn--ghost btn--sm" aria-label={t("memory.add")} title={t("memory.add")} disabled={busy || !adding.trim()}
        ><Plus size={16} /></button
      >
    </form>
  {:else}
    <p class="text-caption">{t("memory.full")}</p>
  {/if}
</section>

<style>
  .section {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px;
  }
  .section.lifted {
    opacity: 0.5;
  }
  /* Where a section dragged over it goes: a bar above or below it. */
  .section.drop-before::before,
  .section.drop-after::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    height: 3px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--glow) 90%, transparent);
  }
  .section.drop-before::before {
    top: -10px;
  }
  .section.drop-after::after {
    bottom: -10px;
  }
  .grip {
    display: grid;
    place-items: center;
    flex: none;
    width: 20px;
    height: 28px;
    margin-left: -8px;
    padding: 0;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-faint);
    cursor: grab;
    /* A touch on it drags the section instead of scrolling the page. */
    touch-action: none;
  }
  .grip:hover,
  .grip:focus-visible {
    color: var(--color-text-primary);
  }
  .grip:active {
    cursor: grabbing;
  }
  header {
    display: flex;
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
    align-items: center;
    gap: 8px;
    min-height: 32px;
    padding: 2px 4px 2px 10px;
    border-radius: var(--radius-sm);
  }
  li:hover {
    background: var(--color-bg-hover-ghost);
  }
  .text {
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
  li .input {
    flex: 1;
  }
  .add {
    display: flex;
    gap: 8px;
  }
  .add .input {
    flex: 1;
    min-width: 0;
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
