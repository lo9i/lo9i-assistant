<script lang="ts">
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import PanelRightOpen from "@lucide/svelte/icons/panel-right-open";
  import Square from "@lucide/svelte/icons/square";
  import SquareTerminal from "@lucide/svelte/icons/square-terminal";
  import X from "@lucide/svelte/icons/x";
  import type { TaskSession } from "$lib/api/types";
  import { overall, shownSession, working } from "$lib/chat/codingTasks";
  import { taskTabs } from "$lib/chat/taskTabs.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { panelWidth } from "$lib/panelWidths.svelte";
  import { iconColor, installedIcon } from "$lib/pluginIcons";
  import PanelDivider from "../PanelDivider.svelte";
  import StatusMark from "../subagents/StatusMark.svelte";
  import TaskSessionView from "./TaskSessionView.svelte";

  // Beside a conversation that started coding tasks: the agents at work, a row per session (the task the assistant
  // started and the turns that followed it up) with its folder and, while it works, Stop (asked inline first), else how
  // it ended and a way to close it; the row picked shows its work as it comes and a box to write to the agent below.
  // Minimized, a thin bar saying how they're doing, which opens it again; the conversation beside it stays the
  // assistant's. Open, the divider before it drags it wider or narrower.
  type Props = { threadId: string; sessions: TaskSession[]; open: boolean; ontoggle: () => void };
  let { threadId, sessions, open, ontoggle }: Props = $props();
  const { client, notices } = useDaemon();
  const shown = $derived(shownSession(sessions, taskTabs.get(threadId)));
  const status = $derived(overall(sessions));
  // The bar names the agent when they're all the same one's.
  const agents = $derived([...new Set(sessions.map((s) => s.name))]);
  // Its accents in the agent's own colour, its plugin's icon's (Claude Code's orange), not the app's: the colour that
  // marks a conversation handed to an agent where its plugin's icon has none.
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const accent = $derived(
    agents.length === 1 ? (iconColor(installedIcon(servers.data, sessions[0].agent)) ?? "var(--color-agent)") : "var(--color-agent)",
  );
  // The session whose Stop is being asked about.
  let stopping = $state<string | null>(null);

  function folder(session: TaskSession): string {
    return session.repository.split("/").filter(Boolean).at(-1) ?? session.repository;
  }

  async function act(action: () => Promise<unknown>): Promise<void> {
    stopping = null;
    try {
      await action();
    } catch (e) {
      notices.report(e);
    }
  }
</script>

{#if open}
  {@const width = panelWidth("tasks")}
  <PanelDivider name="tasks" />
  <aside
    class="panel surface--glass"
    class:sized={width !== undefined}
    style:--chosen-width={width}
    style:--glow={accent}
    style:--color-accent={accent}
    aria-label={t("tasks.title")}
  >
    <header>
      <span class="icon"><SquareTerminal size={14} /></span>
      <span class="heading">{t("tasks.title")}</span>
      <button class="btn btn--ghost btn--icon" title={t("tasks.minimize")} aria-label={t("tasks.minimize")} onclick={ontoggle}
        ><PanelRightClose size={14} /></button
      >
    </header>
    <ul class="sessions" aria-label={t("tasks.sessions")}>
      {#each sessions as session (session.id)}
        <li class="row" class:active={session.id === shown?.id}>
          <button
            type="button"
            class="pick"
            aria-current={session.id === shown?.id}
            title="{session.name} · {session.title}"
            onclick={() => taskTabs.pick(threadId, session.id)}
          >
            <span class="row-title">{session.title}</span>
            <span class="where" title={t("tasks.in", { folder: session.repository })}>{folder(session)}</span>
          </button>
          <span class="end">
            {#if working(session)}
              {#if stopping === session.id}
                <span class="ask">{t("tasks.stopTitle", { agent: session.name })}</span>
                <button class="btn btn--danger btn--sm" onclick={() => act(() => client.tasks.stop(threadId, session.id))}
                  >{t("tasks.stop")}</button
                >
                <button class="btn btn--ghost btn--sm" onclick={() => (stopping = null)}>{t("common.cancel")}</button>
              {:else}
                <button class="btn btn--ghost btn--sm" title={t("tasks.stopText")} onclick={() => (stopping = session.id)}
                  ><Square size={10} fill="currentColor" />{t("tasks.stop")}</button
                >
              {/if}
            {:else}
              <button
                class="btn btn--ghost btn--icon close"
                title={t("tasks.closeHint")}
                aria-label={t("tasks.close")}
                onclick={() => act(() => client.tasks.remove(threadId, session.id))}><X size={12} /></button
              >
              <span title={t(`tasks.status.${session.status}`)}><StatusMark status={session.status} /></span>
            {/if}
          </span>
        </li>
      {/each}
    </ul>
    {#if shown}
      {#key shown.id}<TaskSessionView {threadId} session={shown} />{/key}
    {/if}
  </aside>
{:else}
  <button
    type="button"
    class="rail surface--glass status--{status}"
    style:--glow={accent}
    style:--color-accent={accent}
    title={t("tasks.show")}
    aria-label={t("tasks.show")}
    onclick={ontoggle}
  >
    <PanelRightOpen size={14} />
    <span class="marks">
      {#each sessions as session (session.id)}<StatusMark status={session.status} />{/each}
    </span>
    {#if status === "running"}
      <!-- Working shows as a spinner in the agent's colour, its words only on hover and to a screen reader. -->
      {#if agents.length === 1}<span class="rail-label">{agents[0]}</span>{/if}
      <span class="working" role="img" title={t("tasks.status.running")} aria-label={t("tasks.status.running")}
        ><StatusMark status="running" /></span
      >
    {:else if status}
      <span class="rail-label">{agents.length === 1 ? `${agents[0]} · ` : ""}{t(`tasks.status.${status}`)}</span>
    {/if}
  </button>
{/if}

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    /* Beside the chat and the other panels: when there isn't room for all, each gives way in proportion to its width
     (the chat keeping its least, ChatPanel), and what it holds stays inside it rather than running under the next. */
    flex: 0 1 46%;
    min-width: 0;
    max-width: 760px;
    overflow: hidden;
    min-height: 0;
    height: 100%;
    padding: 10px 8px 8px;
  }
  /* Dragged to a width of its own: that one, the chat keeping some room whatever the window. */
  .panel.sized {
    flex: 0 1 var(--chosen-width);
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
  .heading {
    flex: 1;
    min-width: 0;
    font-size: var(--font-size-sm);
  }
  /* The sessions, a compact row each; past a few, they scroll. */
  .sessions {
    display: flex;
    flex-direction: column;
    flex: none;
    max-height: 140px;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    list-style: none;
    border: 1px solid color-mix(in srgb, var(--color-border) 70%, transparent);
    border-radius: 12px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 30px;
    padding-right: 6px;
    transition: background 0.12s ease;
    --btn-icon-size: 22px;
  }
  .row + .row {
    border-top: 1px solid color-mix(in srgb, var(--color-border) 45%, transparent);
  }
  .row:hover {
    background: var(--color-bg-hover-ghost);
  }
  .row.active {
    background: color-mix(in srgb, var(--glow) 12%, transparent);
  }
  .pick {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
    align-self: stretch;
    padding: 0 0 0 10px;
    border: 0;
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .active .pick {
    color: var(--color-text-primary);
  }
  .row-title,
  .where,
  .ask {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .where {
    flex: 0 2 auto;
    color: var(--color-text-faint);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
  }
  .end {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex: none;
    max-width: 70%;
    min-width: 0;
  }
  .ask {
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
  }
  .end .btn--sm {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
  }
  /* Closing an ended session shows on the row picked or pointed at, so the rows read as their marks. */
  .close {
    visibility: hidden;
  }
  .row.active .close,
  .row:hover .close,
  .close:focus-visible {
    visibility: visible;
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
    border-radius: var(--radius-md);
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
  .working {
    display: flex;
    flex: none;
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
