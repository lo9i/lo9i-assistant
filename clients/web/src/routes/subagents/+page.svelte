<script lang="ts">
  import { page } from "$app/state";
  import Bot from "@lucide/svelte/icons/bot";
  import type { BackgroundSubagent, TaskSession } from "$lib/api/types";
  import { working as taskWorking } from "$lib/chat/codingTasks";
  import { conversationTitle, doing, taskTitle, working } from "$lib/chat/subagents";
  import { clock } from "$lib/clock.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { duration } from "$lib/duration";
  import { localTime } from "$lib/health";
  import { t } from "$lib/i18n.svelte";
  import { iconColor, installedIcon } from "$lib/pluginIcons";
  import Confirm from "$lib/ui/Confirm.svelte";
  import EmptyState from "$lib/ui/EmptyState.svelte";
  import SearchField from "$lib/ui/SearchField.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";
  import { openConversation } from "$lib/ui/openConversation";
  import ActiveOnly from "$lib/ui/chat/subagents/ActiveOnly.svelte";
  import StatusMark from "$lib/ui/chat/subagents/StatusMark.svelte";
  import SubagentView from "$lib/ui/chat/subagents/SubagentView.svelte";
  import TaskSessionView from "$lib/ui/chat/tasks/TaskSessionView.svelte";

  // Every conversation's background subagents (core/background_subagents/) and coding agents' sessions (start_task,
  // core/agent_tasks/beside.py), newest first: what each is doing, the conversation it works for, when it started and
  // ended. The one picked shows on the right as the conversation's side panels show it: a subagent to answer what it
  // waits for, stop it or remove it; a coding session with its work and a box to write to its agent. At first only those
  // still at it are listed; the Active filter off lists those that ended too.
  type Row =
    | { kind: "subagent"; key: string; started: number; subagent: BackgroundSubagent }
    | { kind: "task"; key: string; started: number; session: TaskSession };

  const { client, chats, notices } = useDaemon();
  const subagents = resource((c) => c.subagents.list(), ["subagents"]);
  // A step of theirs comes as `agent_task_progress`, which the line of what each is doing follows.
  const sessions = resource((c) => c.tasks.everywhere(), ["tasks_beside", "agent_task_progress"]);
  // For the title of the conversation each works for.
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  // For the colour of a coding agent's plugin's icon (Claude Code's orange), as beside its conversation.
  const servers = resource((c) => c.mcp.servers(), ["mcp"]);
  const time = clock();
  // A link can open a subagent with ?id=<its id>.
  const linked = page.url.searchParams.get("id");
  let picked = $state<string | null>(linked);
  // A link to one opens it whether it ended or not.
  let activeOnly = $state(linked === null);
  let query = $state("");
  // The coding session whose Stop is being asked about.
  let stopping = $state<TaskSession | null>(null);
  const loaded = $derived(subagents.data && sessions.data ? { subagents: subagents.data, sessions: sessions.data } : null);
  const rows = $derived(
    loaded
      ? [
          ...loaded.subagents.map((s): Row => ({ kind: "subagent", key: s.id, started: Date.parse(s.started_at), subagent: s })),
          ...loaded.sessions.map((s): Row => ({ kind: "task", key: taskKey(s), started: Date.parse(s.started_at), session: s })),
        ].sort((a, b) => b.started - a.started)
      : [],
  );
  const active = $derived(activeOnly ? rows.filter(busy) : rows);
  const shown = $derived(active.filter((r) => searched(r).toLowerCase().includes(query.trim().toLowerCase())));
  const row = $derived(shown.find((r) => r.key === picked) ?? shown[0]);

  function taskKey(session: TaskSession): string {
    return `task:${session.thread_id}:${session.id}`;
  }

  function busy(row: Row): boolean {
    return row.kind === "subagent" ? working(row.subagent) : taskWorking(row.session);
  }

  // By task or conversation, and a coding session by its agent and folder too.
  function searched(row: Row): string {
    if (row.kind === "subagent") return `${row.subagent.task} ${title(row.subagent.thread_id)}`;
    const s = row.session;
    return `${s.name} ${s.title} ${s.repository} ${title(s.thread_id)}`;
  }

  function title(threadId: string): string {
    return threadId === chats.inboxId ? t("subagentsPage.inbox") : conversationTitle(threadId, conversations.data ?? []);
  }

  function folder(session: TaskSession): string {
    return session.repository.split("/").filter(Boolean).at(-1) ?? session.repository;
  }

  function accent(session: TaskSession): string {
    return iconColor(installedIcon(servers.data, session.agent)) ?? "var(--color-agent)";
  }

  async function act(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
    } catch (e) {
      notices.report(e);
    }
  }
</script>

<TopBar title={t("subagents.title")} />

<div class="screen" class:idle={!row}>
  <section class="table-card surface--glass">
    <header class="toolbar">
      <div>
        <h2 class="text-heading">{t("subagentsPage.title")}</h2>
        <p class="text-meta">{t("subagentsPage.hint")}</p>
      </div>
      <div class="filters">
        <ActiveOnly bind:checked={activeOnly} />
        <SearchField bind:value={query} label={t("subagentsPage.search")} />
      </div>
    </header>
    <div class="scroll">
      {#if subagents.error || sessions.error}
        <p class="error-text pad">{subagents.error || sessions.error}</p>
      {:else if loaded && rows.length === 0}
        <EmptyState icon={Bot} title={t("subagentsPage.none")} text={t("subagentsPage.noneHint")} />
      {:else if loaded && active.length === 0}
        <EmptyState icon={Bot} title={t("subagentsPage.noneActive")} text={t("subagentsPage.noneActiveHint")} />
      {:else if loaded}
        <table class="data-table">
          <thead
            ><tr
              ><th>{t("subagentsPage.status")}</th><th>{t("subagentsPage.task")}</th><th>{t("subagentsPage.conversation")}</th><th
                class="hide-narrow">{t("subagentsPage.started")}</th
              ><th class="hide-narrow">{t("subagentsPage.ended")}</th></tr
            ></thead
          >
          <tbody>
            {#each shown as r (r.key)}
              <tr class:selected={r.key === row?.key} onclick={() => (picked = r.key)}>
                {#if r.kind === "subagent"}
                  {@const s = r.subagent}
                  <td>
                    <span class="state status--{s.status}"><StatusMark status={s.status} />{t(`subagents.status.${s.status}`)}</span>
                  </td>
                  <td class="task">
                    <button class="row-button" title={s.task} onclick={() => (picked = r.key)}>{taskTitle(s.task)}</button>
                    {#if doing(s)}<span class="doing text-caption" title={doing(s)}>{doing(s)}</span>{/if}
                  </td>
                  <td class="conversation">{@render conversation(s.thread_id)}</td>
                  <td class="text-label hide-narrow">{localTime(s.started_at)}</td>
                  <td class="text-label hide-narrow">{s.ended_at ? localTime(s.ended_at) : ""}</td>
                {:else}
                  {@const s = r.session}
                  <td>
                    <span class="state status--{s.status}"><StatusMark status={s.status} />{t(`subagents.status.${s.status}`)}</span>
                  </td>
                  <td class="task">
                    <button class="row-button" title="{s.name} · {s.title}" onclick={() => (picked = r.key)}
                      ><span class="agent" style:--agent={accent(s)}>{s.name}</span>{s.title}</button
                    >
                    <span class="doing text-caption" title={s.repository}>{folder(s)}{s.step ? ` · ${s.step}` : ""}</span>
                  </td>
                  <td class="conversation">{@render conversation(s.thread_id)}</td>
                  <td class="text-label hide-narrow">{localTime(s.started_at)}</td>
                  <td class="hide-narrow"></td>
                {/if}
              </tr>
            {:else}
              <tr><td colspan="5" class="text-meta">{t("common.noMatches")}</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  </section>

  <div class="column">
    {#if row?.kind === "subagent"}
      {@const subagent = row.subagent}
      <section class="details surface--glass">
        <dl>
          <dt class="micro-label">{t("subagentsPage.conversation")}</dt>
          <dd>{@render conversation(subagent.thread_id)}</dd>
          <dt class="micro-label">{t("subagentsPage.started")}</dt>
          <dd>{localTime(subagent.started_at)}</dd>
          {#if subagent.ended_at}
            <dt class="micro-label">{t("subagentsPage.ended")}</dt>
            <dd>{localTime(subagent.ended_at)}</dd>
          {/if}
          <dt class="micro-label">{t("subagentsPage.took")}</dt>
          <dd>{duration(subagent.started_at, subagent.ended_at || time.now)}</dd>
        </dl>
        {#key subagent.id}
          <SubagentView id={subagent.id} />
        {/key}
      </section>
    {:else if row?.kind === "task"}
      {@const session = row.session}
      <section class="details surface--glass" style:--glow={accent(session)}>
        <dl>
          <dt class="micro-label">{t("subagentsPage.conversation")}</dt>
          <dd>{@render conversation(session.thread_id)}</dd>
          <dt class="micro-label">{t("subagentsPage.folder")}</dt>
          <dd class="where" title={session.repository}>{folder(session)}</dd>
          <dt class="micro-label">{t("subagentsPage.started")}</dt>
          <dd>{localTime(session.started_at)}</dd>
        </dl>
        <div class="actions">
          {#if taskWorking(session)}
            <button class="btn btn--danger btn--sm" onclick={() => (stopping = session)}>{t("tasks.stop")}</button>
          {:else}
            <button
              class="btn btn--ghost btn--sm"
              title={t("tasks.closeHint")}
              onclick={() => act(() => client.tasks.remove(session.thread_id, session.id))}>{t("subagents.remove")}</button
            >
          {/if}
        </div>
        {#key row.key}
          <TaskSessionView threadId={session.thread_id} {session} />
        {/key}
      </section>
    {:else}
      <section class="placeholder surface--glass">
        <EmptyState icon={Bot} title={t("subagentsPage.noneSelected")} text={t("subagentsPage.noneSelectedHint")} />
      </section>
    {/if}
  </div>
</div>

{#snippet conversation(id: string)}
  {#if id === chats.inboxId}
    <span class="text-label">{title(id)}</span>
  {:else}
    <button
      class="link"
      title={t("app.openItsConversation")}
      onclick={(e) => {
        e.stopPropagation();
        void openConversation(chats, notices, id);
      }}>{title(id)}</button
    >
  {/if}
{/snippet}

{#if stopping}
  {@const session = stopping}
  <Confirm
    title={t("tasks.stopTitle", { agent: session.name })}
    text={t("tasks.stopText")}
    action={t("tasks.stop")}
    onanswer={(yes) => {
      stopping = null;
      if (yes) void act(() => client.tasks.stop(session.thread_id, session.id));
    }}
  />
{/if}

<style>
  .screen {
    display: flex;
    /* Cards take the height of their content, up to the screen; long lists scroll inside. */
    align-items: flex-start;
    gap: 16px;
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  /* With none to show, the row is as tall as the table and the placeholder matches it. */
  .idle {
    height: auto;
    align-items: stretch;
  }
  .placeholder {
    flex: 1;
  }
  /* The table takes three quarters of the width, the subagent the rest. */
  .table-card {
    flex: 3 1 0;
    min-width: 0;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .column {
    flex: 1 1 0;
    align-self: stretch;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 24px;
    min-height: 66px;
    border-bottom: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .filters {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .toolbar p {
    margin: 4px 0 0;
  }
  .scroll {
    overflow-y: auto;
    min-height: 0;
  }
  .data-table thead th {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .pad {
    padding: 24px;
  }
  tr {
    cursor: pointer;
  }
  tr.selected {
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
  }
  tr.selected td:first-child {
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .state {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }
  .status--waiting {
    color: var(--color-warn);
  }
  .task {
    max-width: 0;
    width: 45%;
  }
  .task > * {
    display: block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .doing,
  .where {
    font-family: var(--font-mono);
  }
  /* A coding session's agent, named before its title in its plugin's colour. */
  .agent {
    margin-right: 8px;
    padding: 0 6px;
    border: 1px solid color-mix(in srgb, var(--agent) 45%, transparent);
    border-radius: var(--radius-full);
    color: var(--agent);
    font-size: var(--font-size-xs);
    font-weight: 400;
  }
  .actions {
    display: flex;
    gap: 6px;
  }
  .row-button {
    border: 0;
    background: none;
    padding: 0;
    font-weight: 500;
    text-align: left;
    cursor: pointer;
  }
  .link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--color-accent);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .link:hover {
    text-decoration: underline;
  }
  .details {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-height: 0;
    padding: 20px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    margin: 0;
    align-items: baseline;
  }
  dd {
    margin: 0;
    text-align: right;
    overflow-wrap: anywhere;
  }
  dd .link {
    text-align: right;
  }
  /* Stacked, the page scrolls: each part takes its own height instead of a share of the screen. */
  @media (max-width: 900px) {
    .screen {
      flex-direction: column;
      align-items: stretch;
      height: auto;
    }
    .table-card,
    .column {
      flex: none;
    }
    .details {
      min-height: 360px;
    }
  }
</style>
