<script lang="ts">
  import { resolve } from "$app/paths";
  import Bot from "@lucide/svelte/icons/bot";
  import List from "@lucide/svelte/icons/list";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import PanelRightOpen from "@lucide/svelte/icons/panel-right-open";
  import type { BackgroundSubagent } from "$lib/api/types";
  import { counts, doing, summary, taskTitle, working } from "$lib/chat/subagents";
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
  // the folder panel: its steps as they come, what it waits for, and its answer once it ended. While any is still at it
  // only those show, until the Active filter is turned off; with none at it, those that ended show. Every
  // conversation's are on the Subagents page. Minimized, as the coding tasks' panel: a thin bar with a mark for each and
  // how they're doing, which opens it again.
  type Props = { subagents: BackgroundSubagent[]; open: boolean; ontoggle: () => void };
  let { subagents, open, ontoggle }: Props = $props();
  const time = clock();
  let picked = $state<string | null>(null);
  // The filter as the user set it; until then, on while any is at it.
  let activeOnly = $state<boolean | null>(null);
  const filtered = $derived(activeOnly ?? subagents.some(working));
  const shown = $derived(filtered ? subagents.filter(working) : subagents);
  const now = $derived(summary(subagents));
  // The bar's marks: those at it, then the latest that ended, so a long list keeps it short.
  const MARKS = 8;
  const marked = $derived([...subagents.filter(working), ...subagents.filter((s) => !working(s))].slice(0, MARKS));
  // The divider before it drags it wider or narrower: the list and a subagent open each keep their own width.
  const widthName = $derived(picked === null ? "subagents" : "subagents.view");
  const width = $derived(panelWidth(widthName));
  // One removed meanwhile goes back to the list.
  $effect(() => {
    if (picked !== null && !subagents.some((s) => s.id === picked)) picked = null;
  });
</script>

{#if open}
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
      <button class="btn btn--ghost btn--icon" title={t("subagents.hide")} aria-label={t("subagents.hide")} onclick={ontoggle}
        ><PanelRightClose size={14} /></button
      >
    </header>
    {#if picked !== null}
      <SubagentView id={picked} onback={() => (picked = null)} />
    {:else}
      <div class="filter"><ActiveOnly bind:checked={() => filtered, (v) => (activeOnly = v)} /></div>
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
          {#if filtered && subagents.length > 0}
            <li class="text-caption empty">{t("subagents.noneActive")} {t("subagents.noneActiveHint")}</li>
          {:else}
            <li class="text-caption empty">{t("subagents.none")}</li>
          {/if}
        {/each}
      </ul>
    {/if}
  </aside>
{:else}
  <button
    type="button"
    class="rail surface--glass status--{now.status}"
    title={now.status === "waiting" ? t("subagents.waitingHint", { count: counts(subagents).waiting }) : t("subagents.show")}
    aria-label="{t('subagents.show')}: {now.label}"
    onclick={ontoggle}
  >
    <PanelRightOpen size={14} />
    <Bot size={14} />
    <span class="marks">
      {#each marked as subagent (subagent.id)}<StatusMark status={subagent.status} />{/each}
    </span>
    <span class="rail-label">{t("subagents.title")} · {now.label}</span>
  </button>
{/if}

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
  /* Minimized: a thin bar down the chat's side, as the coding tasks' (TasksPanel), its words read upwards in the colour of
   how they're doing (the cards' --mark). */
  .rail {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    flex: none;
    width: 34px;
    height: 100%;
    padding: 10px 0;
    color: var(--color-text-muted);
    font: inherit;
    cursor: pointer;
    border-radius: var(--radius-md);
    transition: border-color 0.12s ease;
  }
  .rail:hover {
    border-color: color-mix(in srgb, var(--mark) 60%, transparent);
    color: var(--color-text-primary);
  }
  .rail.status--running,
  .rail.status--waiting {
    border-color: color-mix(in srgb, var(--mark) 45%, transparent);
  }
  .marks {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .rail-label {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-height: 0;
    font-size: var(--font-size-xs);
    letter-spacing: 0.02em;
  }
  .rail:not(.status--done) .rail-label {
    color: var(--mark);
  }
  /* Narrow, it covers the chat from the right instead of taking room beside it; minimized, it stays a thin bar. */
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
