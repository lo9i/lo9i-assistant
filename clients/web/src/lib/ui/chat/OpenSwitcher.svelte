<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import MessageSquare from "@lucide/svelte/icons/message-square";
  import MessagesSquare from "@lucide/svelte/icons/messages-square";
  import X from "@lucide/svelte/icons/x";
  import { t } from "$lib/i18n.svelte";
  import { openNow } from "../openNow.svelte";

  // On a phone the sidebar has no room for the conversations open under Chat: this button in Chat's top bar lists them,
  // with any other where something works, to switch to one or close it. Wider screens have them in the sidebar.
  const open = openNow();
  let shown = $state(false);
  let root = $state<HTMLElement>();

  async function pick(item: { key: string | null; threadId: string }): Promise<void> {
    shown = false;
    await open.show(item);
  }

  /** A click anywhere else, or Escape, closes the list. */
  function outside(e: MouseEvent): void {
    if (shown && root && !root.contains(e.target as Node)) shown = false;
  }
</script>

<svelte:window onclick={outside} onkeydown={(e) => e.key === "Escape" && (shown = false)} />

{#if open.items.length}
  <div class="switcher" bind:this={root}>
    <button
      class="btn btn--ghost"
      aria-expanded={shown}
      aria-label={t("nav.openConversations")}
      title={t("nav.openConversations")}
      onclick={() => (shown = !shown)}
    >
      <MessagesSquare size={16} />
      <span class="count">{open.items.length}</span>
      {#if open.waiting}<i class="waiting" aria-label={t("nav.waitingCount", { count: open.waiting })}></i>{/if}
    </button>
    {#if shown}
      <ul class="menu surface--glass" aria-label={t("nav.openConversations")}>
        {#each open.items as entry (entry.key ?? entry.threadId)}
          <li style:--tint={open.tint(entry.threadId)}>
            <button class="entry" class:current={entry.active} aria-current={entry.active ? "true" : undefined} onclick={() => pick(entry)}>
              {#if entry.running}<LoaderCircle size={14} class="spin" aria-label={t("nav.working")} />
              {:else}<MessageSquare size={14} />{/if}
              <span>{entry.title}</span>
              {#if entry.waiting}<i class="waiting" aria-label={t("nav.waiting")}></i>{/if}
            </button>
            {#if entry.key !== null}
              {@const key = entry.key}
              <button class="close" aria-label={t("nav.closeConversation", { title: entry.title })} onclick={() => open.close(key)}
                ><X size={14} /></button
              >
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .switcher {
    position: relative;
  }
  @media (min-width: 681px) {
    .switcher {
      display: none;
    }
  }
  .count {
    font-variant-numeric: tabular-nums;
  }
  .waiting {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--color-accent);
  }
  .menu {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    z-index: 30;
    width: min(320px, calc(100vw - 24px));
    max-height: 60dvh;
    overflow-y: auto;
    margin: 0;
    padding: 6px;
    list-style: none;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.18);
  }
  li {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .entry {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    padding: 9px 10px;
    border: 0;
    border-left: 3px solid var(--tint);
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .entry span {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .entry :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .entry :global(.spin) {
      animation: none;
    }
  }
  .close {
    display: grid;
    place-items: center;
    flex: none;
    width: 34px;
    height: 34px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .entry:hover,
  .entry.current,
  .close:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
</style>
