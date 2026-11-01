<script lang="ts">
  import Bot from "@lucide/svelte/icons/bot";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import type { BackgroundSubagent } from "$lib/api/types";
  import { taskTitle } from "$lib/chat/subagents";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";
  import StatusMark from "./StatusMark.svelte";
  import SubagentView from "./SubagentView.svelte";

  // Beside a conversation that sent subagents off to work in the background: a card for each, newest first, with its
  // task, its status, what it's doing now and for how long. A card opens it in place of the list, as a file opens in
  // the folder panel: its steps as they come, what it waits for, and its answer once it ended.
  type Props = { subagents: BackgroundSubagent[]; onclose: () => void };
  let { subagents, onclose }: Props = $props();
  const time = clock();
  let picked = $state<string | null>(null);
  // One removed meanwhile goes back to the list.
  $effect(() => {
    if (picked !== null && !subagents.some((s) => s.id === picked)) picked = null;
  });

  function doing(subagent: BackgroundSubagent): string {
    if (subagent.status === "waiting") return t("subagents.waitingForYou");
    if (subagent.status === "running") return subagent.step || t("subagents.thinking");
    return subagent.status === "done" ? t("subagents.answered") : subagent.result;
  }
</script>

<aside class="panel surface--glass" class:viewing={picked !== null} aria-label={t("subagents.title")}>
  <header>
    <Bot size={14} />
    <span class="title">{t("subagents.title")}</span>
    <button class="btn btn--ghost btn--icon" title={t("subagents.hide")} aria-label={t("subagents.hide")} onclick={onclose}
      ><PanelRightClose size={14} /></button
    >
  </header>
  {#if picked !== null}
    <SubagentView id={picked} onback={() => (picked = null)} />
  {:else}
    <ul class="cards">
      {#each subagents as subagent (subagent.id)}
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
        <li class="text-caption empty">{t("subagents.none")}</li>
      {/each}
    </ul>
  {/if}
</aside>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 300px;
    flex: none;
    min-height: 0;
    height: 100%;
    padding: 10px 8px;
    transition: width 0.15s ease;
  }
  /* Its steps need more room than its card. */
  .panel.viewing {
    width: min(45%, 560px);
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
    .panel.viewing {
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
