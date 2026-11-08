<script lang="ts">
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import PanelRightOpen from "@lucide/svelte/icons/panel-right-open";
  import SquareTerminal from "@lucide/svelte/icons/square-terminal";
  import type { TaskSession } from "$lib/api/types";
  import { overall, shownSession } from "$lib/chat/codingTasks";
  import { taskTabs } from "$lib/chat/taskTabs.svelte";
  import { t } from "$lib/i18n.svelte";
  import { panelWidth } from "$lib/panelWidths.svelte";
  import PanelDivider from "../PanelDivider.svelte";
  import StatusMark from "../subagents/StatusMark.svelte";
  import TaskSessionView from "./TaskSessionView.svelte";

  // Beside a conversation that started coding tasks: the agents at work, a tab per session (the task the assistant
  // started and the turns that followed it up), each its work as it comes and a box to write to the agent. Minimized,
  // a thin bar saying how they're doing, which opens it again; the conversation beside it stays the assistant's. Open,
  // the divider before it drags it wider or narrower.
  type Props = { threadId: string; sessions: TaskSession[]; open: boolean; ontoggle: () => void };
  let { threadId, sessions, open, ontoggle }: Props = $props();
  const shown = $derived(shownSession(sessions, taskTabs.get(threadId)));
  const status = $derived(overall(sessions));
  // The bar names the agent when they're all the same one's.
  const agents = $derived([...new Set(sessions.map((s) => s.name))]);
</script>

{#if open}
  {@const width = panelWidth("tasks")}
  <PanelDivider name="tasks" />
  <aside class="panel surface--glass" class:sized={width !== undefined} style:--chosen-width={width} aria-label={t("tasks.title")}>
    <header>
      <span class="icon"><SquareTerminal size={14} /></span>
      <div class="tabs" role="tablist" aria-label={t("tasks.sessions")}>
        {#each sessions as session (session.id)}
          <button
            type="button"
            role="tab"
            class="tab"
            class:active={session.id === shown?.id}
            aria-selected={session.id === shown?.id}
            title="{session.name} · {session.title}"
            onclick={() => taskTabs.pick(threadId, session.id)}
          >
            <StatusMark status={session.status} />
            <span class="tab-title">{session.title}</span>
          </button>
        {/each}
      </div>
      <button class="btn btn--ghost btn--icon" title={t("tasks.minimize")} aria-label={t("tasks.minimize")} onclick={ontoggle}
        ><PanelRightClose size={14} /></button
      >
    </header>
    {#if shown}
      {#key shown.id}<TaskSessionView {threadId} session={shown} />{/key}
    {/if}
  </aside>
{:else}
  <button
    type="button"
    class="rail surface--glass status--{status}"
    title={t("tasks.show")}
    aria-label={t("tasks.show")}
    onclick={ontoggle}
  >
    <PanelRightOpen size={14} />
    <span class="marks">
      {#each sessions as session (session.id)}<StatusMark status={session.status} />{/each}
    </span>
    {#if status}
      <span class="rail-label">{agents.length === 1 ? `${agents[0]} · ` : ""}{t(`tasks.status.${status}`)}</span>
    {/if}
  </button>
{/if}

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 0 1 46%;
    min-width: 340px;
    max-width: 760px;
    min-height: 0;
    height: 100%;
    padding: 10px 8px 8px;
  }
  /* Dragged to a width of its own: that one, the chat keeping some room whatever the window. */
  .panel.sized {
    flex: none;
    width: var(--chosen-width);
    max-width: calc(100% - 320px);
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-left: 6px;
    color: var(--color-text-muted);
  }
  .icon {
    display: flex;
    flex: none;
    color: var(--glow);
  }
  .tabs {
    display: flex;
    flex: 1;
    gap: 4px;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: 0 1 auto;
    min-width: 0;
    max-width: 220px;
    padding: 4px 10px;
    border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
    border-radius: var(--radius-full);
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--font-size-sm);
    cursor: pointer;
    transition:
      background 0.12s ease,
      border-color 0.12s ease;
  }
  .tab:hover {
    background: var(--color-bg-hover-ghost);
  }
  .tab.active {
    border-color: color-mix(in srgb, var(--glow) 60%, transparent);
    background: color-mix(in srgb, var(--glow) 12%, transparent);
    color: var(--color-text-primary);
  }
  .tab-title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Minimized: a thin bar down the chat's side, its words read upwards. */
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
    transition: border-color 0.12s ease;
  }
  .rail:hover {
    border-color: color-mix(in srgb, var(--glow) 60%, transparent);
    color: var(--color-text-primary);
  }
  .rail.status--running {
    border-color: color-mix(in srgb, var(--glow) 45%, transparent);
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
  .status--running .rail-label {
    color: var(--glow);
  }
  .status--failed .rail-label {
    color: var(--color-danger);
  }
  /* Narrow, it covers the chat from the right instead of taking room beside it; minimized, it stays a thin bar. */
  @media (max-width: 900px) {
    .panel,
    .panel.sized {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: var(--z-popover);
      width: min(100%, 520px);
      max-width: none;
      min-width: 0;
      background: var(--surface-modal-bg);
      box-shadow: var(--shadow-popover);
    }
  }
</style>
