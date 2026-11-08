<script lang="ts">
  import { resolve } from "$app/paths";
  import Bot from "@lucide/svelte/icons/bot";
  import List from "@lucide/svelte/icons/list";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import type { BackgroundSubagent } from "$lib/api/types";
  import { doing, taskTitle, working } from "$lib/chat/subagents";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import { panelWidth, panelWidths } from "$lib/panelWidths.svelte";
  import PanelDivider from "../PanelDivider.svelte";
  import ActiveOnly from "./ActiveOnly.svelte";
  import StatusMark from "./StatusMark.svelte";
  import SubagentView from "./SubagentView.svelte";

  // Beside a conversation that sent subagents off to work in the background: a card for each, newest first, with its
  // task, its status, what it's doing now and for how long. A card opens it in place of the list, as a file opens in
  // the folder panel: its steps as they come, what it waits for, and its answer once it ended. At first only those still
  // at it show; the Active filter off shows those that ended too. Every conversation's are on the Subagents page.
  type Props = { subagents: BackgroundSubagent[]; onclose: () => void };
  let { subagents, onclose }: Props = $props();
  const time = clock();
  let picked = $state<string | null>(null);
  let activeOnly = $state(true);
  const shown = $derived(activeOnly ? subagents.filter(working) : subagents);
  // The divider before it drags it wider or narrower: the list and a subagent open each keep their own width.
  const widthName = $derived(picked === null ? "subagents" : "subagents.view");
  const width = $derived(panelWidth(widthName));
  // One removed meanwhile goes back to the list.
  $effect(() => {
    if (picked !== null && !subagents.some((s) => s.id === picked)) picked = null;
  });
</script>

<PanelDivider name={widthName} />
<aside
  class="panel surface--glass"
  class:viewing={picked !== null}
  class:sized={width !== undefined}
  class:resizing={panelWidths.dragging === widthName}
  style:--chosen-width={width}
  aria-label={t("subagents.title")}
>
  <header>
    <Bot size={14} />
    <span class="title">{t("subagents.title")}</span>
    <a class="btn btn--ghost btn--icon" href={resolve("/subagents")} title={t("subagents.all")} aria-label={t("subagents.all")}
      ><List size={14} /></a
    >
    <button class="btn btn--ghost btn--icon" title={t("subagents.hide")} aria-label={t("subagents.hide")} onclick={onclose}
      ><PanelRightClose size={14} /></button
    >
  </header>
  {#if picked !== null}
    <SubagentView id={picked} onback={() => (picked = null)} />
  {:else}
    <div class="filter"><ActiveOnly bind:checked={activeOnly} /></div>
    <ul class="cards">
      {#each shown as subagent (subagent.id)}
        <li>
          <button class="card status--{subagent.status}" onclick={() => (picked = subagent.id)}>
            <span class="top">
              <StatusMark status={subagent.status} />
              <span class="status">{t(`subagents.status.${subagent.status}`)}</span>
              <span class="time">{duration(subagent.started_at, subagent.ended_at || time.now)}</span>
            </span>
            <span class="task" title={subagent.task}>{taskTitle(subagent.task)}</span>
            {#if doing(subagent)}<span class="doing" title={doing(subagent)}>{doing(subagent)}</span>{/if}
          </button>
        </li>
      {:else}
        {#if activeOnly && subagents.length > 0}
          <li class="text-caption empty">{t("subagents.noneActive")} {t("subagents.noneActiveHint")}</li>
        {:else}
          <li class="text-caption empty">{t("subagents.none")}</li>
        {/if}
      {/each}
    </ul>
  {/if}
</aside>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    /* Beside the chat and the other panels: when there isn't room for all, each gives way in proportion to its width
     (the chat keeping its least, ChatPanel), and what it holds stays inside it rather than running under the next. */
    width: 300px;
    flex: 0 1 auto;
    min-width: 0;
    overflow: hidden;
    min-height: 0;
    height: 100%;
    padding: 10px 8px;
    transition: width 0.15s ease;
  }
  /* Its steps need more room than its card. */
  .panel.viewing {
    width: min(45%, 560px);
  }
  /* Dragged to a width of its own: that one, the chat keeping some room whatever the window. */
  .panel.sized {
    width: var(--chosen-width);
    max-width: calc(100% - 320px);
  }
  .panel.resizing {
    transition: none;
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 0 0 8px;
    color: var(--color-text-muted);
  }
  .title {
    flex: 1;
    min-width: 0;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  .filter {
    padding: 0 8px;
  }
  .cards {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    list-style: none;
    margin: 0;
    padding: 6px 0 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
    padding: 8px 10px;
    border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
    border-left: 3px solid var(--mark);
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-text-primary) 3%, transparent);
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    --mark: var(--color-text-faint);
  }
  .card:hover {
    background: var(--color-bg-hover-ghost);
  }
  .status--running {
    --mark: var(--color-accent);
  }
  .status--waiting {
    --mark: var(--color-warn);
  }
  .status--done {
    --mark: var(--color-success);
  }
  .status--stopped {
    --mark: var(--color-text-muted);
  }
  .status--failed {
    --mark: var(--color-danger);
  }
  .top {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .status {
    flex: 1;
  }
  .task {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-weight: 600;
    font-size: var(--font-size-sm);
  }
  .doing {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
  }
  .status--waiting .doing {
    font-family: inherit;
    color: var(--color-warn);
  }
  .empty {
    padding: 4px 8px;
  }
  /* Narrow, it covers the chat from the right instead of taking room beside it. */
  @media (max-width: 900px) {
    .panel,
    .panel.viewing,
    .panel.sized {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: var(--z-popover);
      width: min(100%, 420px);
      background: var(--surface-modal-bg);
      box-shadow: var(--shadow-popover);
    }
  }
</style>
